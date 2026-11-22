#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Run the test scripts of an application without Make, from data only
(step G2B-3).

  test.py test -C <app> BOARD=<board> [-n] [--print-env] [VAR=VALUE…]
      run the scripts of TESTS (default: the executable files of
      <app>/tests) one after the other in the application directory, with
      TEST_EXECUTOR and TEST_EXECUTOR_FLAGS in front, with the environment
      Make gives them, as `make -C <app> test` does; the first failing script
      ends the run. -n: print the commands, run nothing (as `make -n`);
      --print-env: print the variables the scripts get from the build system.
      Nothing is built or flashed (flash first with `just flash`).
  test.py test/available -C <app> BOARD=<board> [-n] [VAR=VALUE…]
      exit 0 if the application has tests for the board, as
      `make test/available` (TEST_ON_CI_WHITELIST, TEST_ON_CI_BLACKLIST,
      TESTS), with Make's messages

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
flash data G3-2, terminal and debugger data G2B-1/G2B-2, the test data of
this step: makefiles/tests/tests.test.yaml) and, as for Make, the variables
of the environment. The evaluation is the one of dist/tools/term/term.py;
nothing here runs make, opens a Make file or parses Make syntax. The test
scripts themselves may call make (dist/pythonlibs/testrunner/spawn.py runs
`make cleanterm` and `make reset`, decision T2). Exit status (as Make,
without Make's `make: ***` line): 0; 2 a script or a check fails, or an
error of the configuration (Make's `$(error)`); 3 the request is outside
the data (BUILD_IN_DOCKER=1 where Make runs the tests in Docker: native
boards, which have no data anyway; TEST_DEPS (the terminal's TERMDEPS, e.g.
bootterm), the cases of the terminal: EMULATE=1, IOTLAB_NODE, a board or
programmer without data, an application without data; MAKEFLAGS or MFLAGS
in the environment); a script ended by a signal (Ctrl+C) ends this program
by the same signal after the script ended.

What is algorithm (this file) and what it replaces (Make file:line, base
db4fc1c576):

  probe_tests         makefiles/term_providers.inc.mk PROBE_TESTS (formerly
                      the `TESTS ?=` line, makefiles/tests/tests.inc.mk:9-10)
  probe_riotproject   makefiles/term_providers.inc.mk PROBE_RIOTPROJECT
                      (formerly Makefile.include:66)
  directories         the order of the test data of Makefile.include
                      (test.yaml) and setup_dirs.inc.mk, and setup_dirs.inc.mk:33,
                      :39 (the absolute paths)
  in_docker_goal      tests.inc.mk:26-28, docker.inc.mk:31-33, :41-46
  check_scope         the Docker branch (exit 3), tests.inc.mk:31 (TEST_DEPS)
  recipe_test         tests.inc.mk:31-34 (the loop, `$(Q)` of Makefile.include:270-274)
  recipe_available    tests.inc.mk:37-48 (the conditions are read when Make
                      reads the rule, before makefiles/murdock.inc.mk:40 sets
                      `TEST_ON_CI_WHITELIST ?= all`)
  makeflags           what GNU Make (4.3) puts into MAKEFLAGS, MFLAGS and
                      MAKELEVEL of a recipe of `make -C <app> test VAR=VALUE…`:
                      the flags `r` (Makefile.include:3) and `w` (-C),
                      `--no-print-directory` (Makefile.include:272, QUIET=1),
                      the command line variables in reverse order (blanks and
                      `\\` escaped, `$` doubled) and MAKEOVERRIDES with the
                      directory variables (Makefile.include:82-101,
                      makefiles/setup_dirs.inc.mk:24)
  run                 term.py's run, in the application directory
"""

from __future__ import annotations

import argparse
import glob
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "term"))

# pylint: disable=wrong-import-position
import term as TM  # noqa: E402  (sets up the import path)
import termdata as T  # noqa: E402
import flash as FL  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel, RIOTBASE  # noqa: E402

GOALS = ("test", "test/available")
WHAT = "the tests"
# Makefile.include:82-95 (__DIRECTORY_VARIABLES, in Make's order)
DIRECTORY_VARIABLES = ("RIOTBASE", "RIOTCPU", "RIOTMAKE", "RIOTPKG", "RIOTTOOLS",
                       "RIOTPROJECT", "APPDIR", "BUILD_DIR", "BINDIRBASE", "BINDIR",
                       "PKGDIRBASE", "DLCACHE_DIR")
# the flags of `make -C <app>` with Makefile.include:3 (`--no-builtin-rules`)
FLAG_LETTERS = "rw"
NO_PRINT_DIRECTORY = "--no-print-directory"


# --- probe (makefiles/term_providers.inc.mk) -------------------------------------
def probe_tests(v) -> str:
    """PROBE_TESTS: the files of $(APPDIR)/tests whose name does not end
    with `~` that are regular and executable, sorted (Make's $(wildcard));
    the text of Make's $(foreach): each word of the body with its leading
    blank, the words joined by a blank."""
    pattern = os.path.join(v.get("APPDIR").strip(), "tests", "*[!~]")
    found = [f if os.path.isfile(f) and os.access(f, os.X_OK) else ""
             for f in sorted(glob.glob(pattern))]
    return " ".join(" " + f for f in found)


def probe_riotproject(v) -> str:
    """PROBE_RIOTPROJECT: Make's `$(shell …)` in the calling directory."""
    return TM.shell(f"cd {shlex.quote(v.get('CURDIR'))} && "
                    "{ git rev-parse --show-toplevel 2>/dev/null || pwd; }")


PROVIDERS = dict(TM.PROVIDERS, PROBE_TESTS=probe_tests, PROBE_RIOTPROJECT=probe_riotproject)


def directories(ev):
    """The test data of Makefile.include (RIOTPROJECT, DLCACHE_DIR) and of
    makefiles/setup_dirs.inc.mk (PYTHONPATH), with the absolute paths of
    setup_dirs.inc.mk:33, :39 (`override … := $(abspath …)`) in between."""
    v = ev.v
    ev.run_file(T.data_name(os.path.join(RIOTBASE, "Makefile.include"), "test"))
    for name in ("RIOTPROJECT", "DLCACHE_DIR"):
        path = os.path.normpath(os.path.join(v.get("CURDIR"), v.get(name).strip()))
        v.set(name, path, "simple", origin=v.origin(name))     # origin kept, as `override`
    ev.run_file(T.data_name(os.path.join(v.get("RIOTMAKE").strip(), "setup_dirs.inc.mk"),
                            "test"))


# --- the rules ------------------------------------------------------------------
def in_docker_goal(v, exists=os.path.exists) -> bool:
    """tests.inc.mk:26: `1-0-test` = BUILD_IN_DOCKER, INSIDE_DOCKER
    (docker.inc.mk:41-46: no /.dockerinit, /.dockerenv, /run/.containerenv)
    and `test` in DOCKER_MAKECMDGOALS (docker.inc.mk:31-33: only for a BOARD
    native%). Otherwise Make runs the tests here, as this does."""
    inside = any(exists(f) for f in ("/.dockerinit", "/.dockerenv", "/run/.containerenv"))
    return v.get("BUILD_IN_DOCKER").strip() == "1" and not inside \
        and v.get("BOARD").strip().startswith("native")


def check_scope(v, goal: str):
    """`test` in Docker or with prerequisites: outside the data (exit 3)."""
    if goal != "test":
        return
    if in_docker_goal(v):
        raise OutOfScope("BUILD_IN_DOCKER=1: make runs the tests of this board in Docker "
                         "(not converted to data); run them with make")
    deps = v.words("TEST_DEPS")
    if deps:
        shown = " ".join(rel(d) if os.path.isabs(d) else d for d in deps)
        raise OutOfScope(f"the tests need {shown} to be built first (TEST_DEPS); "
                         "run them with make")


def quiet(v) -> str:
    """$(Q) (Makefile.include:270-274)."""
    return "@" if v.get("QUIET").strip() == "1" else ""


def recipe_test(v) -> list:
    """tests.inc.mk:32-34 as one recipe line (backslash-newline kept, the
    first tab of the next lines removed, as Make passes it to the shell)."""
    return [f"{quiet(v)} for t in {v.get('TESTS')}; do \\\n"
            f"\t{v.get('TEST_EXECUTOR')} {v.get('TEST_EXECUTOR_FLAGS')} $t || exit 1; \\\n"
            "done"]


def recipe_available(v) -> list:
    """tests.inc.mk:37-48."""
    board, q, lines = v.get("BOARD"), quiet(v), []
    whitelist = v.words("TEST_ON_CI_WHITELIST")
    if whitelist and v.get("BOARD").strip() not in whitelist:
        lines += [f'@echo "Board {board} not in TEST_ON_CI_WHITELIST"', f"{q}false"]
    if set(v.words("BOARD") + ["all"]) & set(v.words("TEST_ON_CI_BLACKLIST")):
        lines += [f'@echo "Board {board} is in TEST_ON_CI_BLACKLIST"', f"{q}false"]
    return lines + [f'{q}test -n "{" ".join(v.words("TESTS"))}"']


# --- MAKEFLAGS ------------------------------------------------------------------
def quote_for_env(text: str) -> str:
    """GNU Make's quoting of a command line variable in MAKEFLAGS."""
    out = []
    for char in text:
        if char == "$":
            out.append("$")
        elif char in " \t\\":
            out.append("\\")
        out.append(char)
    return "".join(out)


def makeflags(v, command_line: list, environ: dict) -> dict:
    """MAKEFLAGS, MFLAGS and MAKELEVEL of a recipe of `make -C <app> <goal>
    VAR=VALUE…` (`command_line`: the assignments as typed, in order)."""
    options = [NO_PRINT_DIRECTORY] if quiet(v) else []
    overrides = list(DIRECTORY_VARIABLES)
    boards = os.path.join(RIOTBASE, "boards")
    if os.path.normpath(v.get("RIOTBOARD").strip() or boards) != boards:
        overrides.append("RIOTBOARD")               # makefiles/setup_dirs.inc.mk:24
    words = [quote_for_env(f"{name}={value}") for name, value in reversed(command_line)]
    words += [f"{name}={v.get(name)}" for name in overrides]
    level = int(environ.get("MAKELEVEL", "0") or 0) + 1
    return {"MAKEFLAGS": " ".join([FLAG_LETTERS] + options + ["--"] + words),
            "MFLAGS": " ".join([f"-{FLAG_LETTERS}"] + options),
            "MAKELEVEL": str(level)}


def check_environment(environ: dict):
    """Make merges MAKEFLAGS and MFLAGS of its environment (a call from
    inside make): not converted (exit 3)."""
    for name in ("MAKEFLAGS", "MFLAGS"):
        if environ.get(name, "").strip():
            raise OutOfScope(f"{name} is set in the environment ({environ[name].strip()}); "
                             "run the tests with make")


# --- plan -----------------------------------------------------------------------
def plan_test(app_dir: str, command_line: list, goal: str, environ: dict, report=None,
              isatty=os.isatty) -> dict:
    """What `make -C <app> <goal>` does: the recipe lines, the variables the
    scripts get and Make's warnings (passed to `report` in Make's order,
    before a configuration error)."""
    check_environment(environ)
    variables = dict(command_line)
    ev = TM.evaluate(app_dir, variables, environ, goals=(goal,), what=WHAT, termdeps=False,
                     providers=PROVIDERS)
    v = ev.v
    directories(ev)
    ev.run_file(T.data_name(os.path.join(v.get("RIOTMAKE").strip(), "tests", "tests.inc.mk"),
                            "test"))                       # Makefile.include:723
    messages = [f"{level}: {text}" for level, text in ev.messages if level == "warning"]
    warning = FL.supported_warning(v)
    if warning:
        messages.append(f"warning: {warning}")
    for message in messages if report else []:
        report(message)
    if not v.get("FLASHFILE").strip():          # Makefile.include:470-472
        raise ResolveError(f"FLASHFILE is not defined for this board: {v.get('BOARD').strip()}")
    check_scope(v, goal)
    sh = TM.colours(v, isatty)[3]
    lines = recipe_test(v) if goal == "test" else recipe_available(v)
    env = TM.terminal_environment(ev, goal, environ)
    env.update(makeflags(v, command_line, environ))
    if isatty(1) and isatty(2):                 # GNU Make 4.3 (output to a terminal)
        env["MAKE_TERMOUT"] = env["MAKE_TERMERR"] = os.ttyname(1)
    return {"recipe": lines, "shell": sh, "env": env, "messages": messages,
            "curdir": v.get("CURDIR"), "data": ev.term_read}


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=GOALS)
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--print-env", action="store_true",
                        help="print the variables the scripts get")
    parser.add_argument("variables", nargs="*", metavar="VAR=VALUE")
    args = parser.parse_intermixed_args(argv)
    command_line = []
    for item in args.variables:
        if "=" not in item:
            parser.error(f"not a variable: {item}")
        command_line.append(tuple(item.split("=", 1)))
    if not args.app or "BOARD" not in dict(command_line):
        parser.error(f"{args.command} needs -C <application> and BOARD=<board>")
    return args, command_line


def main(argv=None) -> int:
    args, command_line = parse(sys.argv[1:] if argv is None else argv)
    try:
        result = plan_test(args.app, command_line, args.command, dict(os.environ),
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
    os.chdir(result["curdir"])                  # Make runs the recipe in CURDIR
    return TM.run(result)


if __name__ == "__main__":
    sys.exit(main())
