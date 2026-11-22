#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Start the debugger of an application without Make, from data only (step
G2B-2).

  debug.py debug|debug-server|debug-client -C <app> BOARD=<board> [-n] [--print-env]
           [VAR=VALUE…]
      run DEBUGGER (DEBUGSERVER, DEBUGCLIENT) of the programmer with its
      flags and the environment Make gives it, as `make debug`
      (`make debug-server`, `make debug-client`) does. -n: print the commands,
      run nothing (as `make -n`); --print-env: print the variables the
      debugger gets from the build system. The debugger uses the existing
      image (Make's BINDIR <app>/bin/<board>, or BINDIR=…); nothing is built.

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
flash data G3-2, terminal and debugger data G2B-1, the setsid rule of macOS
of this step in debug.yaml) and, as for Make, the variables of the
environment. The evaluation is the one of dist/tools/term/term.py (the
terminal reads the same debugger data); nothing here runs make, opens a Make
file or parses Make syntax. Exit status (as Make): 0, or the debugger's own
status when it is 0; 2 the debugger is not set (Make's hint), missing or
fails, or an error of the configuration (Make's `$(error)`); 3 the request
is outside the data (DEBUGDEPS: USE_PYCORTEXMDEBUG=1, EMULATE=1, setsid on
macOS; a programmer without debugger data; a board without terminal data); a
debugger ended by a signal (Ctrl+C) ends this program by the same signal
after the debugger ended.

What is algorithm (this file) and what it replaces (Make file:line, base
481caa4b65):

  check_deps          DEBUGDEPS, the prerequisites of debug, debug-server,
                      debug-client (Makefile.include:692, :705, :718) that
                      need a build or a download: exit 3
  check_programmer    Makefile.include:312 (`-include $(PROGRAMMER).inc.mk`):
                      the programmer's debugger data
  check_flashfile     Makefile.include:470-472 (`$(error FLASHFILE is not
                      defined …)` for every goal, e.g. an unknown programmer)
  recipe              Makefile.include:684-720 (the three rules, the hint when
                      the program is not set, check_cmd :565-572)
  run                 term.py's run (Make runs each line with /bin/sh -c, stops
                      at the first failure with exit 2, waits for the debugger
                      on SIGINT/SIGTERM/SIGHUP/SIGQUIT and then ends by it)
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "term"))

# pylint: disable=wrong-import-position
import term as TM  # noqa: E402  (sets up the import path)
import termdata as T  # noqa: E402
import flash as FL  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel  # noqa: E402

GOALS = ("debug", "debug-server", "debug-client")
WHAT = "the debugger"
# goal: (program, flags, description of check_cmd) (Makefile.include:684-720)
PROGRAMS = {
    "debug": ("DEBUGGER", "DEBUGGER_FLAGS", "Debug program"),
    "debug-client": ("DEBUGCLIENT", "DEBUGCLIENT_FLAGS", "Debug client program"),
    "debug-server": ("DEBUGSERVER", "DEBUGSERVER_FLAGS", "Debug server program"),
}
# the hint when the program is not set; Make's lines continue with a
# backslash and the next line's tab removed, as the shell gets them
NOT_SET = ("@echo '$$({var}) is not set. This means that `make debug` is not'\\\n"
           "' supported by your current setup. A common reason is that PROGRAMMER'\\\n"
           "' is set to something like flashing via bootloader, where debugging is'\\\n"
           "' not possible.'")


def check_programmer(v):
    """The programmer's Make file must have debugger data (Makefile.include:312
    reads `$(RIOTMAKE)/tools/$(PROGRAMMER).inc.mk`); one without (e.g. pyocd)
    may set the debugger in Make, which is not read here."""
    programmer = v.get("PROGRAMMER").strip()
    if not programmer:
        return
    path = os.path.join(v.get("RIOTMAKE").strip(), "tools", f"{programmer}.inc.mk")
    if os.path.exists(path) and not os.path.isfile(T.data_name(path, "debug")):
        raise OutOfScope(f"programmer {programmer}: {rel(path)} has no debugger data; "
                         f"open {WHAT} with make")


def check_deps(v):
    """DEBUGDEPS: Make builds or downloads them first (PyCortexMDebug,
    setsid on macOS, the emulator's files); outside the data."""
    deps = v.words("DEBUGDEPS")
    if deps:
        shown = " ".join(rel(d) if os.path.isabs(d) else d for d in deps)
        raise OutOfScope(f"the debugger needs {shown} to be built or fetched first "
                         "(DEBUGDEPS); start it with make")


def recipe(v, goal: str, isatty=os.isatty) -> tuple:
    """The lines of the rule of `goal` (Makefile.include:684-720) as Make
    runs them (`@` hides a line) and the shell that runs them."""
    var, flags, description = PROGRAMS[goal]
    red, reset, echo, sh = TM.colours(v, isatty)
    prog = v.get(var)
    if not prog.strip():
        return [NOT_SET.format(var=var).replace("$$", "$"), "@false"], sh
    check = (f"@command -v {prog} >/dev/null 2>&1 || {{ {echo} '{red}{description} {prog} "
             f"is required but not found in PATH.  Aborting.{reset}'; exit 1;}}")
    return [check, f"{prog} {v.get(flags)}"], sh


def plan_debug(app_dir: str, variables: dict, goal: str, environ: dict, report=None,
               isatty=os.isatty) -> dict:
    """What `make <goal>` does: the recipe lines, the variables the debugger
    gets and Make's warnings (passed to `report` in Make's order, before a
    configuration error)."""
    ev = TM.evaluate(app_dir, variables, environ, goals=(goal,), what=WHAT, termdeps=False)
    v = ev.v
    check_programmer(v)
    check_deps(v)
    messages = [f"{level}: {text}" for level, text in ev.messages if level == "warning"]
    warning = FL.supported_warning(v)
    if warning:
        messages.append(f"warning: {warning}")
    for message in messages if report else []:
        report(message)
    if not v.get("FLASHFILE").strip():          # Makefile.include:470-472
        raise ResolveError(f"FLASHFILE is not defined for this board: {v.get('BOARD').strip()}")
    lines, sh = recipe(v, goal, isatty)
    return {"recipe": lines, "shell": sh, "env": TM.terminal_environment(ev, goal, environ),
            "messages": messages, "data": ev.term_read}


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=GOALS)
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--print-env", action="store_true",
                        help="print the variables the debugger gets")
    parser.add_argument("variables", nargs="*", metavar="VAR=VALUE")
    args = parser.parse_intermixed_args(argv)
    variables = {}
    for item in args.variables:
        if "=" not in item:
            parser.error(f"not a variable: {item}")
        name, value = item.split("=", 1)
        variables[name] = value
    if not args.app or "BOARD" not in variables:
        parser.error(f"{args.command} needs -C <application> and BOARD=<board>")
    return args, variables


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        result = plan_debug(args.app, variables, args.command, dict(os.environ),
                            lambda message: print(message, file=sys.stderr))
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    if args.print_env:
        for name in sorted(result["env"]):
            print(f"{name}={result['env'][name]}")
        return 0
    if args.dry_run:
        for line in result["recipe"]:
            print(FL.shown(line))
        return 0
    return TM.run(result)


if __name__ == "__main__":
    sys.exit(main())
