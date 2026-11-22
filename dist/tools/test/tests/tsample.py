# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G2B-3 (tests without Make) and the golden files of GNU
Make.

The applications of the scope on nrf52840dk have no test scripts (decision
T1); the cases pass stub scripts (the recorder) with TESTS=, as Make reads
TESTS with `?=`. A golden file holds per case:

  ## <case>: make -n <goal> [...]     the commands of the target
  ## <case>: run [...]                `make -C <app> <goal>`: exit status,
                                      output (`make: ***` and the
                                      directory lines left out) and, per
                                      script call, what the recorder saw:
                                      its path and arguments, the working
                                      directory and the variables the test
                                      scripts read (TEST_READS)

Stubs: `git` fails (as outside a work tree: RIOTPROJECT is the application
directory, PROBE_RIOTPROJECT). Paths: @RIOTBASE@, @TMP@, @REC@ (the
recorder). The file ends with `## end`.
"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CLI = os.path.join(TOOL, "test.py")
GOLDEN = os.path.join(HERE, "golden")
BOARD = "nrf52840dk"
APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
USER = "riot"
GOALS = ("test", "test/available")

# what the test scripts read from the environment (decision B of
# 2026-11-22): dist/pythonlibs/testrunner (spawn.py, __init__.py, utils.py),
# the variables of Make's MAKEFLAGS and the directories
DIRECTORIES = ("RIOTBASE", "RIOTCPU", "RIOTMAKE", "RIOTPKG", "RIOTTOOLS", "RIOTPROJECT",
               "APPDIR", "BUILD_DIR", "BINDIRBASE", "BINDIR", "PKGDIRBASE", "DLCACHE_DIR",
               "RIOTBOARD")
TEST_READS = sorted({
    "RIOT_TEST_TIMEOUT", "TESTRUNNER_START_DELAY", "TESTRUNNER_RESET_DELAY",
    "TESTRUNNER_CONNECT_DELAY", "TESTRUNNER_RESET_AFTER_TERM",
    "TESTRUNNER_RESET_BOARD_ON_STARTUP", "TEST_INTERACTIVE_RETRIES",
    "TEST_INTERACTIVE_DELAY", "MAKE", "USEMODULE", "PYTHONPATH", "MAKEFLAGS", "MFLAGS",
    "MAKELEVEL", "BOARD", *DIRECTORIES})


def case(goal="test", variables=None, env=None, apps=tuple(APPS), tests=False):
    """goal, command line variables (in order), environment, applications;
    `tests`: APPDIR=@TMP@/app with test scripts (the probe)."""
    return {"goal": goal, "vars": list((variables or {}).items()), "env": dict(env or {}),
            "apps": tuple(apps), "tests": tests}


HELLO = ("hello-world",)
CASES = {
    # T1: no test scripts: the empty loop
    "empty": case(),
    # the scripts of TESTS, in order, in the application directory
    "two": case(variables={"TESTS": "@REC@ @REC@ arg"}),
    "executor": case(variables={"TESTS": "@REC@", "TEST_EXECUTOR": "sh",
                                "TEST_EXECUTOR_FLAGS": "-e"}, apps=HELLO),
    "quiet0": case(variables={"QUIET": "0", "TESTS": "@REC@"}, apps=HELLO),
    "fails": case(variables={"TESTS": "@REC@ @REC@"}, env={"G2B_TEST_STATUS": "1"}),
    "quoting": case(variables={"TESTS": "@REC@", "X": "p\\q r", "Y": "a$$b"}, apps=HELLO),
    "environment": case(variables={"TESTS": "@REC@", "TESTRUNNER_CONNECT_DELAY": "2"},
                        env={"PYTHONPATH": "/py", "RIOT_TEST_TIMEOUT": "30",
                             "TESTRUNNER_RESET_AFTER_TERM": "1"}, apps=HELLO),
    "probe": case(tests=True, apps=HELLO),
    # T6: Make runs the tests of nrf52840dk here also with BUILD_IN_DOCKER=1
    "docker": case(variables={"BUILD_IN_DOCKER": "1", "TESTS": "@REC@"}, apps=HELLO),
    # T5: test/available
    "available-none": case(goal="test/available"),
    "available": case(goal="test/available", variables={"TESTS": "@REC@"}),
    "available-probe": case(goal="test/available", tests=True, apps=HELLO),
    "whitelist-other": case(goal="test/available",
                            variables={"TESTS": "@REC@", "TEST_ON_CI_WHITELIST": "other"},
                            apps=HELLO),
    "whitelist-all": case(goal="test/available",
                          variables={"TESTS": "@REC@", "TEST_ON_CI_WHITELIST": "all"},
                          apps=HELLO),
    "whitelist-board": case(goal="test/available",
                            variables={"TESTS": "@REC@", "TEST_ON_CI_WHITELIST": BOARD},
                            apps=HELLO),
    "blacklist-all": case(goal="test/available",
                          variables={"TESTS": "@REC@", "TEST_ON_CI_BLACKLIST": "all"},
                          apps=HELLO),
    "blacklist-board": case(goal="test/available",
                            variables={"QUIET": "0", "TESTS": "@REC@",
                                       "TEST_ON_CI_WHITELIST": f"other {BOARD}",
                                       "TEST_ON_CI_BLACKLIST": BOARD}, apps=HELLO),
}


def cases(app: str) -> dict:
    return {name: c for name, c in CASES.items() if app in c["apps"]}


def golden_path(app: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{BOARD}.txt")


def title(name: str, app_dir: str, c: dict, what: str) -> str:
    shown = " ".join(shlex.quote(f"{k}={v}") for k, v in c["vars"])
    env = " ".join(shlex.quote(f"env:{k}={v}") for k, v in c["env"].items())
    extra = "APPDIR=@TMP@/app" if c["tests"] else ""
    words = " ".join(w for w in (app_dir, extra, shown, env) if w)
    return f"## {name}: {what} [{words}]"


# --- stubs ------------------------------------------------------------------------
RECORDER = """#!/bin/sh
# recorder in place of a test script (step G2B-3 tests)
{{
  printf 'script %s' "$0"
  for a in "$@"; do printf ' [%s]' "$a"; done
  printf '\\ncwd %s\\n' "$(pwd)"
  for n in {names}; do
    eval "set=\\${{$n+x}}"
    if [ -n "$set" ]; then eval "printf '  %s=[%s]\\n' $n \\"\\$$n\\""; else printf '  %s unset\\n' $n; fi
  done
}} >> "$G2B_TEST_LOG"
exit "${{G2B_TEST_STATUS:-0}}"
"""
GIT_STUB = "#!/bin/sh\n# stub of git (step G2B-3 tests): not a work tree\nexit 128\n"


def write_executable(path: str, text: str, mode=True):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    if mode:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class Run:
    """A temporary directory with the recorder, the stub git, HOME and (for
    the probe) an application directory with test scripts."""

    def __init__(self, root: str, app_dir: str, c: dict, tmp: str):
        self.root, self.app_dir, self.c, self.tmp = root, app_dir, c, tmp
        self.rec = os.path.join(tmp, "rec")
        self.log = os.path.join(tmp, "test.log")
        self.home = os.path.join(tmp, "home")
        self.stubs = os.path.join(tmp, "stubs")
        for directory in (self.home, self.stubs):
            os.makedirs(directory, exist_ok=True)
        write_executable(self.rec, RECORDER.format(names=" ".join(TEST_READS)))
        write_executable(os.path.join(self.stubs, "git"), GIT_STUB)
        if c["tests"]:
            tests = os.path.join(tmp, "app", "tests")
            os.makedirs(os.path.join(tests, "04dir"))
            for name, executable in (("01-run", True), ("02-backup~", True),
                                     ("03-noexec", False), ("05-run", True)):
                write_executable(os.path.join(tests, name),
                                 RECORDER.format(names=" ".join(TEST_READS)), executable)

    def value(self, text: str) -> str:
        return text.replace("@REC@", self.rec).replace("@TMP@", self.tmp)

    def assignments(self) -> list:
        extra = [f"APPDIR={self.tmp}/app"] if self.c["tests"] else []
        return [f"BOARD={BOARD}"] + extra + [f"{k}={self.value(v)}" for k, v in self.c["vars"]]

    def env(self) -> dict:
        env = {"PATH": os.pathsep.join([self.stubs, "/usr/local/bin", "/usr/bin", "/bin"]),
               "HOME": self.home, "LC_ALL": "C", "USER": USER, "TMPDIR": self.tmp,
               "G2B_TEST_LOG": self.log}
        env.update({k: self.value(v) for k, v in self.c["env"].items()})
        return env

    def make_argv(self, extra: list) -> list:
        return ["make", "-C", self.app_dir, *extra, *self.assignments()]

    def tool_argv(self, extra: list) -> list:
        return [sys.executable, CLI, *extra, "-C", self.app_dir, *self.assignments()]

    def norm(self, text: str) -> str:
        for path, name in sorted(((self.root, "@RIOTBASE@"), (self.rec, "@REC@"),
                                  (self.tmp, "@TMP@")), key=lambda p: -len(p[0])):
            text = text.replace(path, name)
        return text

    def call(self, argv: list) -> tuple:
        """(exit status, output lines, recorder lines)."""
        if os.path.exists(self.log):
            os.remove(self.log)
        res = subprocess.run(argv, cwd=self.root, env=self.env(), capture_output=True,
                             text=True, stdin=subprocess.DEVNULL, check=False)
        out = [line for line in self.norm(res.stdout + res.stderr).split("\n")
               if line and not line.startswith("make: ***")
               and not line.startswith("make: Entering directory")
               and not line.startswith("make: Leaving directory")]
        rec = []
        if os.path.exists(self.log):
            with open(self.log, encoding="utf-8") as file:
                rec = [self.norm(line) for line in file.read().split("\n") if line]
        return res.returncode, out, rec


def sections_of(run: Run, name: str, tool: bool) -> dict:
    """The two sections of a case, from Make or (tool) from test.py."""
    c, goal = run.c, run.c["goal"]
    argv = run.tool_argv if tool else run.make_argv
    dry = [goal, "-n"] if tool else ["-n", goal]
    status, out, _ = run.call(argv(dry))
    result = {title(name, run.app_dir, c, f"make -n {goal}"): [f"## exit: {status}", *out]}
    status, out, rec = run.call(argv([goal]))
    result[title(name, run.app_dir, c, "run")] = [f"## exit: {status}", *out, *rec]
    return result


def record_app(root: str, app: str) -> list:
    lines = []
    for name, c in cases(app).items():
        with tempfile.TemporaryDirectory(prefix="g2b-test-") as tmp:
            for head, body in sections_of(Run(root, APPS[app], c, tmp), name, False).items():
                lines += [head, *body]
    return lines


# --- golden files ------------------------------------------------------------------
def read_golden(path: str) -> dict:
    """{section title: [lines]}."""
    with open(path, encoding="utf-8") as file:
        lines = file.read().split("\n")
    if "## end" not in lines:
        raise ValueError(f"{path}: no `## end` line")
    lines = lines[:lines.index("## end")]
    sections, current = {}, None
    for line in lines:
        if line.startswith("## ") and not line.startswith("## exit:"):
            current = sections.setdefault(line, [])
        elif current is not None and line:
            current.append(line)
    return sections
