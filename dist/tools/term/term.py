#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Open the terminal of an application without Make, from data only (step
G2B-1).

  term.py term -C <app> BOARD=<board> [-n] [--print-env] [VAR=VALUE…]
  term.py cleanterm -C <app> BOARD=<board> [-n] [--print-env] [VAR=VALUE…]
      run the terminal program of RIOT_TERMINAL (default pyterm) with the
      flags, the port and the environment Make gives it, as `make term`
      (`make cleanterm`: pyterm without its logging and prefixes) does.
      -n: print the commands, run nothing (as `make -n`); --print-env: print
      the variables the terminal gets from the build system. The terminal
      uses the existing image where it needs one (native, semihosting:
      Make's BINDIR <app>/bin/<board>, or BINDIR=…); nothing is built.
  term.py generate [--check] [DATA…]
      write (check) the Make adapters generated from the terminal and
      debugger data (all data files of the repository without arguments)

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
flash data G3-2, terminal and debugger data of this step, see termdata.py)
and, as for Make, the variables of the environment. Nothing here runs make,
opens a Make file or parses Make syntax. Exit status (as Make): 0; 2 the
terminal program is missing or fails, or an error of the configuration
(Make's `$(error)`); 3 the request is outside the data; a terminal ended
by a signal (Ctrl+C) ends this program by the same signal.

What is algorithm (this file) and what it replaces (Make file:line, base
481caa4b65):

  environment         Make's variables of the environment (origin environment:
                      `?=` keeps them, `=` replaces them, the command line wins)
  probes              makefiles/term_providers.inc.mk (formerly the `$(shell …)`
                      of makefiles/tools/serial.inc.mk:28, :38, :64 and
                      boards/common/nrf52/Makefile.include:12)
  TermEvaluator       the order of reading: Makefile.include:312 (programmer,
                      flash and debugger data), :316 (serial.inc.mk), :454
                      (DEBUG_ELFFILE); in a Make file its flash, debugger and
                      terminal adapters before its build part
  check_scope         Makefile.include:318-325 (EMULATE), :248 (IOTLAB_NODE),
                      riotboot, suit; TERMDEPS (prerequisites that need a build,
                      bootterm); boards without terminal data
  TERMTEE             Makefile.include:659-661
  cleanterm           Makefile.include:671-676 (`export PYTERMFLAGS +=`, no TERMENV)
  recipe              Makefile.include:662-669 (`term`, check_cmd :565-572 with
                      the colours of makefiles/color.inc.mk)
  terminal_environment  `export` of Make: makefiles/vars.inc.mk (list in
                      makefiles/vars.build.yaml), command line and environment
                      variables, target-export-variables of
                      makefiles/utils/variables.mk
  run                 Make runs each recipe line with /bin/sh -c, stops at the
                      first failure (exit 2), and on SIGINT/SIGTERM/SIGHUP/SIGQUIT
                      waits for the terminal and ends by the signal
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "flash"))

# pylint: disable=wrong-import-position
import termdata as T  # noqa: E402  (sets up the import path)
import flash as FL  # noqa: E402
import flashdata as F  # noqa: E402
import buildeval  # noqa: E402
import pipeline  # noqa: E402
import plan as P  # noqa: E402
import resolver  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel, RIOTBASE  # noqa: E402

GOALS = ("term", "cleanterm")
ENVIRONMENT = "environment"
# variables of the environment GNU Make does not take as its own
NOT_IMPORTED = {"SHELL", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEFILES", "MAKEOVERRIDES",
                "CURDIR", "MAKECMDGOALS", "MAKE_TERMOUT", "MAKE_TERMERR"}
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Makefile.include:673 (`cleanterm: export PYTERMFLAGS += …`)
CLEANTERM_PYTERMFLAGS = "--no-reconnect --noprefix --no-repeat-command-on-empty-line"
# makefiles/utils/ansi.mk
ANSI_RED, ANSI_RESET = r"\033[1;31m", r"\033[0m"
SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)


# --- probes (makefiles/term_providers.inc.mk) -------------------------------------
def shell(command: str) -> str:
    """Make's `$(shell …)`: /bin/sh -c, the output with its newlines as
    blanks and the last ones removed; stderr is not captured."""
    res = subprocess.run(["/bin/sh", "-c", command], stdout=subprocess.PIPE, text=True,
                         check=False)
    return res.stdout.rstrip("\n").replace("\r\n", " ").replace("\n", " ")


def probe_tty_detected(v) -> str:
    return shell(f"{v.get('TTY_SELECT_CMD')} || echo 'no-tty-detected no-serial-detected'")


def probe_date_time(_v) -> str:
    return shell("date +%Y-%m-%d_%H.%M.%S")


def probe_gdb_status(v) -> str:
    return shell(f"{v.get('GDBPREFIX')}gdb -v > /dev/null 2>&1; echo $?")


def probe_tty_usbmodem(_v) -> str:
    return " ".join(sorted(set(glob.glob("/dev/tty.usbmodem*"))))


PROVIDERS = dict(P.PROVIDERS)
PROVIDERS.update(PROBE_TTY_DETECTED=probe_tty_detected, PROBE_DATE_TIME=probe_date_time,
                 PROBE_TTY_USBMODEM=probe_tty_usbmodem,
                 PROBE_GDB_STATUS=probe_gdb_status)


class TermVariables(buildeval.BuildVariables):
    """The build variables with the value `{word: {var, index}}`."""

    def term(self, term) -> str:
        if T.is_word(term):
            body = term["word"]
            words = self.words(body["var"])
            index = body["index"]
            if index == -1:
                return words[-1] if words else ""
            return words[index - 1] if len(words) >= index else ""
        return super().term(term)


class TermEvaluator(FL.FlashEvaluator):
    """The flash evaluator of G3-2 that also reads the debugger and terminal
    data: an included Make file's flash, debugger and terminal data (the
    adapters its first statements include) before its build data; inside
    such data an include reads only the data of the named file."""

    def __init__(self, variables, curdir: str):
        super().__init__(variables, curdir)
        self.term_read: list = []

    def load(self, yaml_path: str) -> list:
        if not T.is_data_name(yaml_path):
            return super().load(yaml_path)
        try:
            rules = T.load(yaml_path)
        except ValueError as err:
            raise ResolveError(str(err)) from None
        self.read.append(rel(yaml_path))
        self.term_read.append(rel(yaml_path))
        return rules

    def in_flash_data(self) -> bool:
        """Inside flash, debugger or terminal data (where `export` is the
        target export of the flash data)."""
        return bool(self.stack) and (F.is_data_name(self.stack[-1])
                                     or T.is_data_name(self.stack[-1]))

    @staticmethod
    def data_files(path: str) -> list:
        """The flash, debugger and terminal data of a Make file, in the order
        the Make file includes their adapters."""
        files = []
        for name in ([F.data_name] + [lambda p, k=k: T.data_name(p, k) for k in T.KINDS]):
            try:
                data = name(path)
            except ValueError:
                continue
            if os.path.isfile(data):
                files.append(data)
        return files

    def include_one(self, path: str, optional: bool, where: str):
        if rel(path) in self.hooks:
            # an algorithm (Makefile.include: build_system of evaluate(), which
            # reads its debugger data where Make does)
            buildeval.BuildEvaluator.include_one(self, path, optional, where)
            return
        files = self.data_files(path)
        if self.in_flash_data():
            if files:
                for data in files:
                    self.run_file(data)
            elif os.path.exists(path):
                raise OutOfScope(f"{where}: includes {rel(path)}, which has no flash, "
                                 "debugger or terminal data")
            elif not optional:
                raise ResolveError(f"{where}: {rel(path)}: no such file")
            return
        for data in files:
            self.run_file(data)
        buildeval.BuildEvaluator.include_one(self, path, optional, where)
        if self.stack and rel(self.stack[-1]) == "build.yaml" and \
                rel(path) == f"cpu/{self.v.get('CPU').strip()}/Makefile.include":
            self.programmer_file()
            self.serial_file()

    def programmer_file(self):
        """Makefile.include:312: `-include $(RIOTMAKE)/tools/$(PROGRAMMER).inc.mk`
        (its flash and debugger data)."""
        programmer = self.v.get("PROGRAMMER").strip()
        if not programmer:
            return
        path = os.path.join(self.v.get("RIOTMAKE").strip(), "tools", f"{programmer}.inc.mk")
        files = self.data_files(path)
        if files:
            for data in files:
                self.run_file(data)
        elif os.path.exists(path):
            raise OutOfScope(f"programmer {programmer}: {rel(path)} has no flash or debugger "
                             "data; open the terminal with make")

    def serial_file(self):
        """Makefile.include:316: `include $(RIOTMAKE)/tools/serial.inc.mk`."""
        path = os.path.join(self.v.get("RIOTMAKE").strip(), "tools", "serial.inc.mk")
        data = T.data_name(path, "term")
        if not os.path.isfile(data):
            raise OutOfScope(f"{rel(path)} has no terminal data ({rel(data)})")
        self.run_file(data)

    def condition(self, cond: dict) -> bool:
        (key, value), = cond.items()
        if key == "command" and "name" in value:
            return FL.command_found(value["name"])
        return super().condition(cond)


def import_environment(v, environ: dict):
    """Make's variables of the environment (recursive, origin environment)."""
    for name, value in environ.items():
        if NAME_RE.match(name) and name not in NOT_IMPORTED:
            v.set(name, value, "recursive", origin=ENVIRONMENT)


def check_scope(v):
    """Requests whose terminal settings are not in the data."""
    if v.get("IOTLAB_NODE").strip():
        raise OutOfScope(f"IOTLAB_NODE={v.get('IOTLAB_NODE').strip()}: IoT-LAB "
                         "(dist/testbed-support/makefile.iotlab.single.inc.mk) is not "
                         "converted to data")
    if v.get("EMULATE").strip() == "1":
        raise OutOfScope("EMULATE=1: the emulator (makefiles/tools/$(RIOT_EMULATOR).inc.mk) "
                         "is not converted to data")
    if "riotboot" in v.words("FEATURES_USED"):
        raise OutOfScope("riotboot (makefiles/boot/riotboot.mk) is not converted to data")
    if "suit" in v.words("USEMODULE"):
        raise OutOfScope("suit (makefiles/suit.inc.mk) is not converted to data")


def check_board(v):
    """The board's Make file must have terminal data: a board without it may
    set the terminal in Make (e.g. native64), which is not read here."""
    boarddir = v.get("BOARDDIR").strip()
    data = T.data_name(os.path.join(boarddir, "Makefile.include"), "term")
    if not os.path.isfile(data):
        raise OutOfScope(f"board {v.get('BOARD').strip()}: no terminal data ({rel(data)}); "
                         "open the terminal with make")


def evaluate(app_dir: str, variables: dict, environ: dict) -> TermEvaluator:
    """The variables of Make for `term` (plan.evaluate_application with the
    flash, debugger and terminal data)."""
    v = TermVariables(PROVIDERS)
    import_environment(v, environ)
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = TermEvaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)

    def build_system():
        pipeline.prelude(ev)
        check_board(v)
        pipeline.application(ev, info_goal=False)
        P.directories(v)
        check_scope(v)
        ev.run_file(os.path.join(RIOTBASE, "makefiles", "pseudomodules.build.yaml"))
        ev.run_file(os.path.join(RIOTBASE, "build.yaml"))
        # Makefile.include:454 (DEBUG_ELFFILE), :629 (programmer.inc.mk)
        ev.run_file(T.data_name(os.path.join(RIOTBASE, "Makefile.include"), "debug"))
        ev.run_file(F.data_name(os.path.join(RIOTBASE, "makefiles", "tools",
                                             "programmer.inc.mk")))
    resolver._run_application(ev, build_system)   # pylint: disable=protected-access
    check_scope(v)
    deps = v.words("TERMDEPS")
    if deps:
        raise OutOfScope(f"the terminal needs {' '.join(rel(d) if os.path.isabs(d) else d for d in deps)} "
                         "to be built first (TERMDEPS); open it with make")
    return ev


def colours(v, isatty) -> tuple:
    """makefiles/color.inc.mk: (COLOR_RED, COLOR_RESET, COLOR_ECHO, SHELL)."""
    if v.get("CC_NOCOLOR").strip() != "1" and isatty(1) and isatty(2):
        if v.get("OS").strip() == "Darwin":
            return ANSI_RED, ANSI_RESET, "echo -e", "bash"
        return ANSI_RED, ANSI_RESET, "/usr/bin/env echo -e", "/bin/sh"
    return "", "", FL.ECHO, "/bin/sh"


def recipe(v, goal: str, isatty=os.isatty) -> tuple:
    """The two lines of `term`/`cleanterm` (Makefile.include:662-676) as Make
    runs them (`@` hides a line) and the shell that runs them."""
    red, reset, echo, sh = colours(v, isatty)
    prog = v.get("TERMPROG")
    check = (f"@command -v {prog} >/dev/null 2>&1 || {{ {echo} '{red}Terminal program {prog} "
             f"is required but not found in PATH.  Aborting.{reset}'; exit 1;}}")
    words = [v.get("TERMPROG"), v.get("TERMFLAGS"), v.get("TERMTEE")]
    if goal == "term":
        words.insert(0, v.get("TERMENV"))
    return [check, " ".join(words)], sh


def terminal_environment(ev, goal: str, environ: dict) -> dict:
    """What Make adds to the environment of the terminal: the exported
    variables (vars.build.yaml), the command line variables, the variables
    of the environment with their value in Make, and the variables of
    target-export-variables (the GNU Make 4.3 rule of flash.py)."""
    v = ev.v
    env = P.exported(v, v.words("BUILD_EXPORTED"))
    env.update(P.command_line(v))
    for name in environ:     # with Make's value, also when a Make file replaced it
        if NAME_RE.match(name) and name not in NOT_IMPORTED and v.defined(name):
            env[name] = v.get(name)
    for targets, names in ev.exports:
        for name in names:
            if v.defined(name):
                env[name] = v.get(name)
            elif goal in targets:
                env.setdefault(name, "")
    if goal == "cleanterm":
        env["PYTERMFLAGS"] = v.get("PYTERMFLAGS")
    return env


def plan_term(app_dir: str, variables: dict, goal: str, environ: dict, report=None,
              isatty=os.isatty) -> dict:
    """What `make term` (`make cleanterm`) does: the recipe lines, the
    variables the terminal gets and Make's warnings (passed to `report` in
    Make's order, before a configuration error)."""
    ev = evaluate(app_dir, variables, environ)
    v = ev.v
    messages = [f"{level}: {text}" for level, text in ev.messages if level == "warning"]
    warning = FL.supported_warning(v)
    if warning:
        messages.append(f"warning: {warning}")
    for message in messages if report else []:
        report(message)
    if v.get("TERMLOG").strip() or v.get("TERMTEE").strip():      # Makefile.include:659-661
        v.set("TERMTEE", "| tee -a ${TERMLOG}", "conditional")
    if goal == "cleanterm":                                        # Makefile.include:673
        v.add("PYTERMFLAGS", CLEANTERM_PYTERMFLAGS)
    lines, sh = recipe(v, goal, isatty)
    return {"recipe": lines, "shell": sh, "env": terminal_environment(ev, goal, environ),
            "messages": messages, "terminal": v.get("RIOT_TERMINAL").strip(),
            "termprog": v.get("TERMPROG").strip(), "data": ev.term_read}


# --- running ----------------------------------------------------------------------------
def run_line(argv: list, env: dict) -> tuple:
    """Run one recipe line as Make does: the terminal shares the process
    group (Ctrl+C reaches it from the tty); a signal to this process is
    remembered (SIGTERM passed on), the line is waited for. Returns (exit
    status, signal received or None)."""
    received = []
    proc = None

    def handler(sig, _frame):
        received.append(sig)
        if sig == signal.SIGTERM and proc is not None:
            proc.send_signal(sig)
    old = {sig: signal.signal(sig, handler) for sig in SIGNALS}
    try:
        proc = subprocess.Popen(argv, env=env)   # pylint: disable=consider-using-with
        status = proc.wait()
    finally:
        for sig, previous in old.items():
            signal.signal(sig, previous)
    return status, (received[0] if received else None)


def die_by(sig: int):
    """End this process by the signal (as Make does after an interrupt)."""
    sys.stdout.flush()
    sys.stderr.flush()
    signal.signal(sig, signal.SIG_DFL)
    os.kill(os.getpid(), sig)
    signal.pause()


def run(result: dict) -> int:
    env = dict(os.environ)
    env.update(result["env"])
    for line in result["recipe"]:
        if not line.lstrip().startswith("@"):
            print(FL.shown(line), flush=True)
        status, sig = run_line([result["shell"], "-c", FL.shown(line)], env)
        if sig is not None:
            die_by(sig)
        if status != 0:
            return 2
    return 0


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=GOALS + ("generate",))
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--print-env", action="store_true",
                        help="print the variables the terminal gets")
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
        parser.error(f"{args.command} needs -C <application> and BOARD=<board>")
    return args, variables


def cmd_generate(check: bool, files: list = None) -> int:
    stale = 0
    for path in files or T.all_data():
        target = T.adapter_name(path)
        try:
            text = T.expected_adapter(path)
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
        print("Change the terminal or debugger data, never the adapter; run "
              "`just generate-term-data`.", file=sys.stderr)
    return 1 if stale else 0


def cmd_term(args, variables: dict) -> int:
    result = plan_term(args.app, variables, args.command, dict(os.environ),
                       lambda message: print(message, file=sys.stderr))
    if args.print_env:
        for name in sorted(result["env"]):
            print(f"{name}={result['env'][name]}")
        return 0
    if args.dry_run:
        for line in result["recipe"]:
            print(FL.shown(line))
        return 0
    return run(result)


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "generate":
            return cmd_generate(args.check, [os.path.abspath(f) for f in args.variables])
        return cmd_term(args, variables)
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
