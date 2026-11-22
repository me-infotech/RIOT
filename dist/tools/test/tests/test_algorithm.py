#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A8: the rules of test.py, each on its own.

A1 probe_tests: the regular executable files of $(APPDIR)/tests whose name
   does not end with `~`, sorted, with the blanks of Make's $(foreach)
A2 probe_riotproject: the git top directory of the calling directory, or
   the calling directory
A3 check_scope (T6): exit 3 for `test` when Make would run it in Docker
   (BUILD_IN_DOCKER=1, not in a container, BOARD native%) or with TEST_DEPS,
   not for test/available; check_environment: MAKEFLAGS/MFLAGS of the
   environment exit 3
A4 recipe_test / quiet: the loop of tests.inc.mk:32-34, `@` only with QUIET=1
A5 recipe_available: whitelist (empty: no check), blacklist (board or all),
   `test -n` with TESTS stripped
A6 makeflags: flags, --no-print-directory with QUIET=1, the command line in
   reverse order quoted as GNU Make does, the directory variables (and
   RIOTBOARD when it is not <RIOTBASE>/boards), MFLAGS, MAKELEVEL + 1
A7 plan_test: the export set (target export of TESTRUNNER_RESET_AFTER_TERM
   as empty, PYTHONPATH, MAKE_TERMOUT/MAKE_TERMERR with a terminal), the
   working directory, exit 2 for a failing script and for an unknown
   programmer (Make's `$(error)`), exit 3 for the terminal's cases
A8 main: exit status of the command line (0, 2, 3)
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import tsample as S  # noqa: E402
import test as TT  # noqa: E402
from buildeval import OutOfScope  # noqa: E402

HELLO = os.path.join(S.RIOTBASE, S.APPS["hello-world"])


class FakeVars:
    """The few calls of the rules on the variables."""

    def __init__(self, **values):
        self.values = values

    def get(self, name):
        return self.values.get(name, "")

    def words(self, name):
        return self.get(name).split()


def run_main(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    old, cwd = dict(os.environ), os.getcwd()
    os.environ.update(env or {})
    try:
        with redirect_stdout(out), redirect_stderr(err):
            status = TT.main(argv)
    finally:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(old)
    return status, out.getvalue(), err.getvalue()


class ProbeTest(unittest.TestCase):
    """A1, A2."""

    def test_probe_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            tests = os.path.join(tmp, "tests")
            os.makedirs(os.path.join(tests, "c-dir"))
            for name, mode in (("b-run", 0o755), ("a-run", 0o755), ("d~", 0o755),
                               ("e-plain", 0o644), (".hidden", 0o755)):
                path = os.path.join(tests, name)
                open(path, "w", encoding="utf-8").close()
                os.chmod(path, mode)
            self.assertEqual(TT.probe_tests(FakeVars(APPDIR=tmp)),
                             f" {tests}/a-run  {tests}/b-run    ")
            self.assertEqual(TT.probe_tests(FakeVars(APPDIR=os.path.join(tmp, "none"))), "")

    def test_probe_riotproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(TT.probe_riotproject(FakeVars(CURDIR=tmp)), tmp)
            subprocess.run(["git", "init", "-q", tmp], check=True)
            sub = os.path.join(tmp, "a")
            os.makedirs(sub)
            self.assertEqual(TT.probe_riotproject(FakeVars(CURDIR=sub)),
                             os.path.realpath(tmp))


class ScopeTest(unittest.TestCase):
    """A3."""

    def test_check_scope(self):
        TT.check_scope(FakeVars(), "test")
        TT.check_scope(FakeVars(BUILD_IN_DOCKER="1", TEST_DEPS="x"), "test/available")
        TT.check_scope(FakeVars(BUILD_IN_DOCKER="0", BOARD="native64"), "test")
        TT.check_scope(FakeVars(BUILD_IN_DOCKER="1", BOARD=S.BOARD), "test")   # local, as Make
        for values in ({"BUILD_IN_DOCKER": "1", "BOARD": "native64"},
                       {"TEST_DEPS": "/x/bootterm"}):
            with self.subTest(values=values), self.assertRaises(OutOfScope):
                TT.check_scope(FakeVars(**values), "test")

    def test_in_docker_goal(self):
        native = FakeVars(BUILD_IN_DOCKER="1", BOARD="native32")
        self.assertTrue(TT.in_docker_goal(native, exists=lambda f: False))
        for f in ("/.dockerinit", "/.dockerenv", "/run/.containerenv"):
            self.assertFalse(TT.in_docker_goal(native, exists=lambda g, f=f: g == f))
        self.assertFalse(TT.in_docker_goal(FakeVars(BUILD_IN_DOCKER="1", BOARD=S.BOARD),
                                           exists=lambda f: False))

    def test_check_environment(self):
        TT.check_environment({"MAKEFLAGS": " ", "MFLAGS": ""})
        for name in ("MAKEFLAGS", "MFLAGS"):
            with self.subTest(name=name), self.assertRaises(OutOfScope):
                TT.check_environment({name: "-j4"})


class RecipeTest(unittest.TestCase):
    """A4, A5."""

    def test_recipe_test(self):
        self.assertEqual(TT.recipe_test(FakeVars(QUIET="1", TESTS="a b", TEST_EXECUTOR="py",
                                                 TEST_EXECUTOR_FLAGS="-x")),
                         ["@ for t in a b; do \\\n\tpy -x $t || exit 1; \\\ndone"])
        self.assertEqual(TT.recipe_test(FakeVars(QUIET="0"))[0][:10], " for t in ")

    def test_recipe_available(self):
        board = {"BOARD": "b", "TESTS": " x  y ", "QUIET": "1"}
        self.assertEqual(TT.recipe_available(FakeVars(**board)), ['@test -n "x y"'])
        self.assertEqual(TT.recipe_available(FakeVars(**board, TEST_ON_CI_WHITELIST="a b")),
                         ['@test -n "x y"'])
        self.assertEqual(TT.recipe_available(FakeVars(**board, TEST_ON_CI_WHITELIST="all")),
                         ['@echo "Board b not in TEST_ON_CI_WHITELIST"', "@false",
                          '@test -n "x y"'])
        for black in ("all", "c b"):
            self.assertEqual(TT.recipe_available(FakeVars(**board, TEST_ON_CI_BLACKLIST=black)),
                             ['@echo "Board b is in TEST_ON_CI_BLACKLIST"', "@false",
                              '@test -n "x y"'])
        self.assertEqual(TT.recipe_available(FakeVars(**board, TEST_ON_CI_BLACKLIST="c")),
                         ['@test -n "x y"'])
        self.assertEqual(TT.recipe_available(FakeVars(BOARD="b", QUIET="0")), ['test -n ""'])


class MakeflagsTest(unittest.TestCase):
    """A6."""

    def values(self, **extra):
        values = {n: f"/d/{n}" for n in TT.DIRECTORY_VARIABLES}
        values.update({"RIOTBOARD": os.path.join(TT.RIOTBASE, "boards"), "QUIET": "1"})
        values.update(extra)
        return FakeVars(**values)

    def test_makeflags(self):
        dirs = " ".join(f"{n}=/d/{n}" for n in TT.DIRECTORY_VARIABLES)
        got = TT.makeflags(self.values(), [("BOARD", "b"), ("X", "p\\q r\t$")], {})
        self.assertEqual(got, {
            "MAKEFLAGS": f"rw --no-print-directory -- X=p\\\\q\\ r\\\t$$ BOARD=b {dirs}",
            "MFLAGS": "-rw --no-print-directory", "MAKELEVEL": "1"})
        got = TT.makeflags(self.values(QUIET="0", RIOTBOARD="/other"), [("BOARD", "b")],
                           {"MAKELEVEL": "2"})
        self.assertEqual(got, {"MAKEFLAGS": f"rw -- BOARD=b {dirs} RIOTBOARD=/other",
                               "MFLAGS": "-rw", "MAKELEVEL": "3"})


class PlanTest(unittest.TestCase):
    """A7."""

    def test_environment_and_directory(self):
        tty = lambda fd: True  # noqa: E731
        old = os.ttyname
        os.ttyname = lambda fd: "/dev/pts/9"
        try:
            plan = TT.plan_test(HELLO, [("BOARD", S.BOARD)], "test",
                                {"PYTHONPATH": "/py", "PATH": os.environ["PATH"]}, isatty=tty)
        finally:
            os.ttyname = old
        env = plan["env"]
        self.assertEqual(env["TESTRUNNER_RESET_AFTER_TERM"], "")
        self.assertEqual(env["PYTHONPATH"], f"{TT.RIOTBASE}/dist/pythonlibs/:/py")
        self.assertEqual(env["DLCACHE_DIR"] if "DLCACHE_DIR" in env else None, None)
        self.assertEqual(env["MAKE_TERMOUT"], "/dev/pts/9")
        self.assertEqual(env["MAKE_TERMERR"], "/dev/pts/9")
        self.assertEqual(plan["curdir"], HELLO)
        self.assertIn(f"DLCACHE_DIR={TT.RIOTBASE}/.dlcache", env["MAKEFLAGS"])
        plan = TT.plan_test(HELLO, [("BOARD", S.BOARD), ("TESTRUNNER_RESET_AFTER_TERM", "1")],
                            "test/available", {}, isatty=lambda fd: False)
        self.assertEqual(plan["env"]["TESTRUNNER_RESET_AFTER_TERM"], "1")
        self.assertNotIn("MAKE_TERMOUT", plan["env"])
        plan = TT.plan_test(HELLO, [("BOARD", S.BOARD)], "test/available", {},
                            isatty=lambda fd: False)
        self.assertNotIn("TESTRUNNER_RESET_AFTER_TERM", plan["env"])
        plan = TT.plan_test(HELLO, [("BOARD", S.BOARD), ("DLCACHE_DIR", "x/../y")], "test",
                            {}, isatty=lambda fd: False)            # setup_dirs.inc.mk:39
        self.assertIn(f" DLCACHE_DIR=x/../y BOARD={S.BOARD} ", plan["env"]["MAKEFLAGS"])
        self.assertTrue(plan["env"]["MAKEFLAGS"].endswith(
            f" DLCACHE_DIR={HELLO}/y"))


class MainTest(unittest.TestCase):
    """A7, A8."""

    def test_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "s")
            S.write_executable(script, "#!/bin/sh\npwd > \"$0.cwd\"\nexit $G2B_S\n")
            base = ["test", "-C", HELLO, f"BOARD={S.BOARD}", f"TESTS={script}"]
            self.assertEqual(run_main(base, {"G2B_S": "0"})[0], 0)
            with open(script + ".cwd", encoding="utf-8") as file:
                self.assertEqual(file.read().strip(), HELLO)
            self.assertEqual(run_main(base, {"G2B_S": "1"})[0], 2)
            self.assertEqual(run_main(base + ["BUILD_IN_DOCKER=1"], {"G2B_S": "0"})[0], 0)
            for extra, env in ((["PROGRAMMER=nosuch"], {}),):
                self.assertEqual(run_main(base + extra, env)[0], 2)
            for extra, env in ((["EMULATE=1"], {}), (["IOTLAB_NODE=x"], {}),
                               (["RIOT_TERMINAL=bootterm"], {}),
                               ([], {"MAKEFLAGS": "-k"})):
                with self.subTest(extra=extra, env=env):
                    status, _, err = run_main(base + extra, env)
                    self.assertEqual(status, 3, err)
            self.assertEqual(run_main(["test/available", "-C", HELLO, f"BOARD={S.BOARD}"])[0],
                             2)
            self.assertEqual(run_main(["test/available", "-C", os.path.join(S.RIOTBASE, "examples/basic/blinky"),
                                       f"BOARD={S.BOARD}", "TESTS=x"])[0], 3)


if __name__ == "__main__":
    unittest.main()
