#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Make a binary distribution without Make, from data only (step G3-3).

  bindist.py bindist -C <app> BOARD=<board> [-B <dir>] [-j N] [-n] [--no-build]
             [VAR=VALUE…]
      build the application with CMake and Ninja (step G3-1) in Make's
      BINDIR (default <app>/bin/<board>, where Make's recipe takes the
      objects and the binary from), then create <app>/bindist as Make's
      target `bindist` does. -n: print the commands, run nothing;
      --no-build: use the existing build products (as `make -o all bindist`
      in a tree without bindist/)
  bindist.py generate [--check] [DIST_DATA…]
      write (check) the Make adapters generated from the distribution data
      (all distribution data files of the repository without arguments)

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
distribution data `<x>.dist.yaml`, see distdata.py). Nothing here runs make,
opens a Make file or parses Make syntax. Exit status: 0; 1 usage or a failed
command; 2 an error of the configuration; 3 the request is outside the data.

What is algorithm (this file) and what it replaces (Make file:line):

  DistEvaluator    makefiles/bindist.inc.mk:4 (the distribution data is read
                   where Make includes its adapter, before the build part)
  check_scope      makefiles/docker.inc.mk (BUILD_IN_DOCKER); building from
                   a distribution (Makefile.distcheck, bindist.build.yaml)
                   stops in the build evaluator
  recipe           makefiles/bindist.inc.mk:14-23 (`bindist: all`), run line
                   by line with /bin/sh -c in the application directory, as
                   Make runs a recipe (the blank line 21 is no command)
  environment      `export` of Make: makefiles/vars.inc.mk (list in
                   makefiles/vars.build.yaml) and the command line variables
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import distdata as D  # noqa: E402  (sets up the import path)
import buildeval  # noqa: E402
import pipeline  # noqa: E402
import plan as P  # noqa: E402
import resolver  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel, RIOTBASE  # noqa: E402

CMAKE_GEN = os.path.join(D.TOOLS, "cmake_gen", "cmake_gen.py")
DIST_DIR = "bindist"


class DistEvaluator(buildeval.BuildEvaluator):
    """The build evaluator of G3-1 that also reads the distribution data:
    when a Make file with distribution data is included, that data (the
    first statement of the Make file: the include of its adapter) is read
    before the build data."""

    def __init__(self, variables, curdir: str):
        super().__init__(variables, curdir)
        self.dist_read: list = []

    def load(self, yaml_path: str) -> list:
        if not D.is_data_name(yaml_path):
            return super().load(yaml_path)
        try:
            rules = D.load(yaml_path)
        except ValueError as err:
            raise ResolveError(str(err)) from None
        self.read.append(rel(yaml_path))
        self.dist_read.append(rel(yaml_path))
        return rules

    def include_one(self, path: str, optional: bool, where: str):
        try:
            data = D.data_name(path)
        except ValueError:
            data = None
        if data and os.path.isfile(data):
            self.run_file(data)
        super().include_one(path, optional, where)


def check_scope(v):
    """Requests whose distribution is not in the data."""
    if v.get("BUILD_IN_DOCKER").strip() == "1":
        raise OutOfScope("BUILD_IN_DOCKER=1 is not converted to data")


def evaluate(app_dir: str, variables: dict) -> DistEvaluator:
    """The variables of Make for `bindist` (plan.evaluate_application with
    the distribution data)."""
    v = buildeval.BuildVariables(P.PROVIDERS)
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = DistEvaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)

    def build_system():
        pipeline.prelude(ev)
        pipeline.application(ev, info_goal=False)
        P.directories(v)
        check_scope(v)
        ev.run_file(os.path.join(RIOTBASE, "makefiles", "pseudomodules.build.yaml"))
        ev.run_file(os.path.join(RIOTBASE, "build.yaml"))
    resolver._run_application(ev, build_system)   # pylint: disable=protected-access
    check_scope(v)
    return ev


def recipe(v) -> list:
    """The command lines of `bindist` (makefiles/bindist.inc.mk:15-23) with
    Make's variables expanded, as Make passes them to the shell: `$$` is
    `$`; a backslash-newline stays, the recipe tab after it is removed."""
    get = lambda name: v.get(name).strip()  # noqa: E731
    return [
        f"@mkdir -p {DIST_DIR}",
        f"@for i in {v.get('DIST_FILES')} ; do \\\n"
        f"\techo Copying $i to {DIST_DIR}. ; \\\n"
        f"\tcp -a --parents $i {DIST_DIR} ; \\\n"
        "\tdone",
        f"@cp -a bin/{get('BOARD')}/{get('APPLICATION')}.bin {DIST_DIR}",
        f"@echo \"BINDIST_RIOT_VERSION={v.get('RIOT_VERSION')}\" > {DIST_DIR}/Makefile.distcheck",
        f"@echo \"BINDIST_GIT_HEAD=$(git -C {v.get('RIOTBASE')} describe)\" >> "
        f"{DIST_DIR}/Makefile.distcheck",
    ]


def shown(line: str) -> str:
    """The line without Make's prefixes `@`, `-`, `+` (what `make -n` prints
    and what the shell runs)."""
    line = line.lstrip()
    while line[:1] in ("@", "-", "+"):
        line = line[1:].lstrip()
    return line


def recipe_environment(v) -> dict:
    """What Make adds to the environment of a recipe: the exported variables
    (vars.build.yaml) and the command line variables."""
    env = P.exported(v, v.words("BUILD_EXPORTED"))
    env.update(P.command_line(v))
    return env


def plan_bindist(app_dir: str, variables: dict) -> dict:
    """What `make bindist` does after `all`."""
    ev = evaluate(app_dir, variables)
    v = ev.v
    return {"recipe": recipe(v), "env": recipe_environment(v), "curdir": v.get("CURDIR").strip(),
            "bindir": v.get("BINDIR").strip(), "dist_files": v.words("DIST_FILES"),
            "data": ev.dist_read}


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("bindist", "generate"))
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-B", dest="builddir", help="build directory (Make's BINDIR)")
    parser.add_argument("-j", dest="jobs", type=int, default=2, help="parallel jobs (build)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--no-build", action="store_true",
                        help="use the existing build products")
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
    if not args.app or "BOARD" not in variables:
        parser.error("bindist needs -C <application> and BOARD=<board>")
    return args, variables


def cmd_generate(check: bool, files: list = None) -> int:
    stale = 0
    for path in files or D.all_data():
        target = D.adapter_name(path)
        try:
            text = D.expected_adapter(path)
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
        print("Change the distribution data, never the adapter; run `just generate-dist-data`.",
              file=sys.stderr)
    return 1 if stale else 0


def cmd_bindist(args, variables: dict) -> int:
    if args.builddir:
        variables = dict(variables, BINDIR=os.path.abspath(args.builddir))
    result = plan_bindist(args.app, variables)
    if args.dry_run:
        for line in result["recipe"]:
            print(shown(line))
        return 0
    if not args.no_build:
        # `bindist: all`: the build of step G3-1 in Make's BINDIR, where the
        # recipe's bin/$(BOARD) paths name the build products
        build = [sys.executable, CMAKE_GEN, "build", "-C", args.app, "-B", result["bindir"],
                 "-j", str(args.jobs)] + [f"{k}={v}" for k, v in variables.items()
                                          if k != "BINDIR"]
        if subprocess.run(build, check=False).returncode != 0:
            return 1
    env = dict(os.environ)
    env.update(result["env"])
    for line in result["recipe"]:
        if not line.lstrip().startswith("@"):
            print(shown(line), flush=True)
        status = subprocess.run(["/bin/sh", "-c", shown(line)], cwd=result["curdir"], env=env,
                                check=False).returncode
        if status != 0:
            return 1
    return 0


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "generate":
            return cmd_generate(args.check, [os.path.abspath(f) for f in args.variables])
        return cmd_bindist(args, variables)
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
