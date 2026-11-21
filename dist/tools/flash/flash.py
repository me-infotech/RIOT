#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Flash an application without Make, from data only (step G3-2).

  flash.py flash -C <app> BOARD=<board> [-B <dir>] [-j N] [-n] [--print-env]
           [--no-build] [VAR=VALUE…]
      build the application with CMake and Ninja (step G3-1, build directory
      <dir>, default <app>/bin/cmake-<board>), then run the flasher command
      of the programmer (PROGRAMMER=…, default: the board's choice) with the
      environment Make gives it. -n: print the flash commands, run nothing;
      --print-env: print the variables the flasher gets from the build
      system; --no-build: flash the existing image (as `make -o all flash`)
  flash.py generate [--check] [FLASH_DATA…]
      write (check) the Make adapters generated from the flash data (all
      flash data files of the repository without arguments)

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
flash data `flash.yaml`/`<x>.flash.yaml`, see flashdata.py). Nothing here
runs make, opens a Make file or parses Make syntax. Exit status: 0; 1 usage,
a failed command or a missing flasher; 2 an error of the configuration; 3
the request is outside the data.

What is algorithm (this file) and what it replaces (Make file:line, base
5f5b94ff9c):

  check_scope            Makefile.include:309-321 (IOTLAB_NODE), :580-588
                         (riotboot, suit), makefiles/tools/serial.inc.mk:5-34
                         (MOST_RECENT_PORT), makefiles/docker.inc.mk (BUILD_IN_DOCKER)
  FlashEvaluator         Makefile.include:371-377 (board and CPU Make files,
                         then `-include $(RIOTMAKE)/tools/$(PROGRAMMER).inc.mk`),
                         :774 (programmer.inc.mk)
  supported_warning      Makefile.include:392-403
  FLASHFILE check        Makefile.include:602-604
  recipe                 Makefile.include:711-717 (check_cmd), :776-787
                         (default-flash-recipe, `flash: all $(FLASHDEPS)`)
  flasher_environment    `export` of Make: makefiles/vars.inc.mk (list in
                         makefiles/vars.build.yaml), command line variables,
                         target-export-variables of makefiles/utils/variables.mk
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import flashdata as F  # noqa: E402  (sets up the import path)
import buildeval  # noqa: E402
import pipeline  # noqa: E402
import plan as P  # noqa: E402
import resolver  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel, RIOTBASE  # noqa: E402

CMAKE_GEN = os.path.join(F.TOOLS, "cmake_gen", "cmake_gen.py")
GOAL = "flash"
# Make's COLOR_ECHO without a colour terminal (makefiles/color.inc.mk:14)
ECHO = "/usr/bin/env echo"


class FlashEvaluator(buildeval.BuildEvaluator):
    """The build evaluator of G3-1 that also reads the flash data: when a
    Make file is included, its flash data (first statement of the Make file:
    the include of the adapter) is read before its build data; an include
    inside flash data reads only the flash data of the named file."""

    def __init__(self, variables, curdir: str):
        super().__init__(variables, curdir)
        self.stack: list = []
        self.exports: list = []        # (target words, variable names)
        self.flash_read: list = []

    # -- files ---------------------------------------------------------------------
    def load(self, yaml_path: str) -> list:
        if not F.is_data_name(yaml_path):
            return super().load(yaml_path)
        try:
            rules = F.load(yaml_path)
        except ValueError as err:
            raise ResolveError(str(err)) from None
        self.read.append(rel(yaml_path))
        self.flash_read.append(rel(yaml_path))
        return rules

    def run_file(self, yaml_path: str):
        self.stack.append(yaml_path)
        try:
            super().run_file(yaml_path)
        finally:
            self.stack.pop()

    def in_flash_data(self) -> bool:
        return bool(self.stack) and F.is_data_name(self.stack[-1])

    def include_one(self, path: str, optional: bool, where: str):
        try:
            data = F.data_name(path)
        except ValueError:
            data = None
        if self.in_flash_data():
            if data and os.path.isfile(data):
                self.run_file(data)
            elif os.path.exists(path):
                raise OutOfScope(f"{where}: includes {rel(path)}, which has no flash data "
                                 f"({rel(data) if data else 'no flash data name'})")
            elif not optional:
                raise ResolveError(f"{where}: {rel(path)}: no such file")
            return
        if data and os.path.isfile(data):
            self.run_file(data)
        super().include_one(path, optional, where)
        if self.stack and rel(self.stack[-1]) == "build.yaml" and \
                rel(path) == f"cpu/{self.v.get('CPU').strip()}/Makefile.include":
            self.programmer_file()

    def programmer_file(self):
        """Makefile.include:376-377: `-include $(RIOTMAKE)/tools/$(PROGRAMMER).inc.mk`
        (after the board's and the CPU's Make files)."""
        programmer = self.v.get("PROGRAMMER").strip()
        if not programmer:
            return
        path = os.path.join(self.v.get("RIOTMAKE").strip(), "tools", f"{programmer}.inc.mk")
        data = F.data_name(path)
        if os.path.isfile(data):
            self.run_file(data)
        elif os.path.exists(path):
            raise OutOfScope(f"programmer {programmer}: {rel(path)} has no flash data "
                             f"({rel(data)}); flash it with make")

    # -- rules ---------------------------------------------------------------------
    def condition(self, cond: dict) -> bool:
        (key, value), = cond.items()
        if key == "command":
            return command_found(self.v.get(value["var"]))
        return super().condition(cond)

    def run(self, rules: list, where: str = "rules"):
        for rule in rules:
            # the flash construct `export: {targets, vars}`; the build data's
            # `export: [NAMES]` (schema 4, step G0-3) is the evaluator's
            if "export" in rule and self.in_flash_data():
                exp = rule["export"]
                self.exports.append((self.v.text(exp["targets"]).split(), list(exp["vars"])))
            else:
                super().run([rule], where)


def command_found(name: str) -> bool:
    """`$(shell command -v NAME)` is not empty: the same question to the
    same shell (/bin/sh, Make's SHELL)."""
    if not name.strip():
        return False
    res = subprocess.run(["/bin/sh", "-c", f"command -v {name}"], capture_output=True,
                         text=True, check=False)
    return bool(res.stdout.strip())


def check_scope(v):
    """Requests whose flash settings are not in the data."""
    for name, why in (("IOTLAB_NODE", "IoT-LAB flashing (makefiles/iotlab.single.inc.mk)"),
                      ("MOST_RECENT_PORT", "serial port detection (makefiles/tools/serial.inc.mk)")):
        value = v.get(name).strip()
        if value and (name != "MOST_RECENT_PORT" or value == "1"):
            raise OutOfScope(f"{name}={value}: {why} is not converted to data")
    if v.get("BUILD_IN_DOCKER").strip() == "1":
        raise OutOfScope("BUILD_IN_DOCKER=1 is not converted to data")
    if "riotboot" in v.words("FEATURES_USED"):
        raise OutOfScope("riotboot (makefiles/boot/riotboot.mk) is not converted to data")
    if "suit" in v.words("USEMODULE"):
        raise OutOfScope("suit (makefiles/suit.inc.mk) is not converted to data")
    if v.words("FLASHDEPS"):
        raise OutOfScope(f"FLASHDEPS ({v.get('FLASHDEPS').strip()}) are not converted to data")


def evaluate(app_dir: str, variables: dict) -> FlashEvaluator:
    """The variables of Make for `flash` (plan.evaluate_application with the
    flash data; Makefile.include:774 programmer.inc.mk at the end)."""
    v = buildeval.BuildVariables(P.PROVIDERS)
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = FlashEvaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)

    def build_system():
        pipeline.prelude(ev)
        pipeline.application(ev, info_goal=False)
        P.directories(v)
        check_scope(v)
        ev.run_file(os.path.join(RIOTBASE, "makefiles", "pseudomodules.build.yaml"))
        ev.run_file(os.path.join(RIOTBASE, "build.yaml"))
        ev.run_file(F.data_name(os.path.join(RIOTBASE, "makefiles", "tools",
                                             "programmer.inc.mk")))
    resolver._run_application(ev, build_system)   # pylint: disable=protected-access
    check_scope(v)
    return ev


def supported_warning(v) -> str:
    """Makefile.include:392-403."""
    programmer = v.get("PROGRAMMER").strip()
    supported = v.get("PROGRAMMERS_SUPPORTED").strip()
    if v.get("RIOT_CI_BUILD").strip() != "1" and programmer != "iotlab" and supported \
            and programmer not in supported.split():
        return (f"'{programmer}' programmer is not supported by this board. "
                f"Supported programmers: '{supported}'")
    return ""


def recipe(v) -> list:
    """The two lines of `flash-recipe` (Makefile.include:711-717, 776-781),
    as Make runs them (`@` hides a line, `make -n` prints it without)."""
    if not v.get("FLASHFILE").strip():
        raise ResolveError(f"FLASHFILE is not defined for this board: {v.get('BOARD').strip()}")
    flasher = v.get("FLASHER")
    check = (f"@command -v {flasher} >/dev/null 2>&1 || {{ {ECHO} 'Flash program {flasher} "
             "is required but not found in PATH.  Aborting.'; exit 1;}")
    return [check, v.get("PROGRAMMER_FLASH").strip()]


def shown(line: str) -> str:
    """The line without Make's prefixes `@`, `-`, `+` (what `make -n` prints
    and what the shell runs)."""
    line = line.lstrip()
    while line[:1] in ("@", "-", "+"):
        line = line[1:].lstrip()
    return line


def flasher_environment(ev) -> dict:
    """What Make adds to the environment of the flasher: the exported
    variables (vars.build.yaml), the command line variables and the
    variables of target-export-variables. GNU Make (4.3) exports the global
    variable for every target once a target-specific `export V ?=` names
    it; an undefined one is exported (empty) for the targets named."""
    v = ev.v
    env = P.exported(v, v.words("BUILD_EXPORTED"))
    env.update(P.command_line(v))
    for targets, names in ev.exports:
        for name in names:
            if v.defined(name):
                env[name] = v.get(name)
            elif GOAL in targets:
                env.setdefault(name, "")
    return env


def plan_flash(app_dir: str, variables: dict, report=None) -> dict:
    """What `make flash` does after `all`: the recipe lines, the variables
    the flasher gets and Make's warnings (passed to `report` before a
    configuration error, in Make's order)."""
    ev = evaluate(app_dir, variables)
    v = ev.v
    messages = [f"{level}: {text}" for level, text in ev.messages if level == "warning"]
    warning = supported_warning(v)
    if warning:
        messages.append(f"warning: {warning}")
    for message in messages if report else []:
        report(message)
    return {"recipe": recipe(v), "env": flasher_environment(ev), "messages": messages,
            "programmer": v.get("PROGRAMMER").strip(), "flasher": v.get("FLASHER").strip(),
            "flashfile": v.get("FLASHFILE").strip(), "data": ev.flash_read}


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("flash", "generate"))
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-B", dest="builddir", help="build directory")
    parser.add_argument("-j", dest="jobs", type=int, default=2, help="parallel jobs (build)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--print-env", action="store_true",
                        help="print the variables the flasher gets")
    parser.add_argument("--no-build", action="store_true", help="flash the existing image")
    parser.add_argument("--check", action="store_true", help="generate: only check")
    parser.add_argument("variables", nargs="*", metavar="VAR=VALUE|FILE")
    args = parser.parse_intermixed_args(argv)
    variables = {}
    if args.command == "generate":
        return args, variables
    for item in args.variables:
        if "=" not in item:
            parser.error(f"not a variable: {item}")
        name, value = item.split("=", 1)
        variables[name] = value
    if args.command == "flash" and (not args.app or "BOARD" not in variables):
        parser.error("flash needs -C <application> and BOARD=<board>")
    return args, variables


def cmd_generate(check: bool, files: list = None) -> int:
    stale = 0
    for path in files or F.all_data():
        target = F.adapter_name(path)
        try:
            text = F.expected_adapter(path)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            stale += 1
            continue
        current = None
        if os.path.exists(target):
            with open(target, encoding="utf-8") as file:
                current = file.read()
        if current == text:
            continue
        if check:
            print(f"{rel(target)} is not up to date with {os.path.basename(path)}",
                  file=sys.stderr)
            stale += 1
        else:
            with open(target, "w", encoding="utf-8") as file:
                file.write(text)
            print(f"wrote {rel(target)}")
    if stale and check:
        print("Change the flash data, never the adapter; run `just generate-flash-data`.",
              file=sys.stderr)
    return 1 if stale else 0


def builddir(args, variables: dict) -> str:
    """The build directory of `just build` (cmake_gen.py builddir())."""
    return os.path.abspath(args.builddir or os.path.join(
        args.app, "bin", f"cmake-{variables['BOARD']}"))


def cmd_flash(args, variables: dict) -> int:
    directory = builddir(args, variables)
    if not args.no_build and not args.dry_run and not args.print_env:
        build = [sys.executable, CMAKE_GEN, "build", "-C", args.app, "-B", directory,
                 "-j", str(args.jobs)] + [f"{k}={v}" for k, v in variables.items()]
        if subprocess.run(build, check=False).returncode != 0:
            return 1
    result = plan_flash(args.app, dict(variables, BINDIR=directory),
                        lambda message: print(message, file=sys.stderr))
    if args.print_env:
        for name in sorted(result["env"]):
            print(f"{name}={result['env'][name]}")
        return 0
    if args.dry_run:
        for line in result["recipe"]:
            print(shown(line))
        return 0
    env = dict(os.environ)
    env.update(result["env"])
    for line in result["recipe"]:
        if not line.lstrip().startswith("@"):
            print(shown(line), flush=True)
        status = subprocess.run(["/bin/sh", "-c", shown(line)], env=env,
                                check=False).returncode
        if status != 0:
            return 1
    return 0


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "generate":
            return cmd_generate(args.check, [os.path.abspath(f) for f in args.variables])
        return cmd_flash(args, variables)
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
