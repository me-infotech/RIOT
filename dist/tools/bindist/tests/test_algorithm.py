#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A5: the algorithm of bindist.py (what is not data).

A1 read order: the distribution data is read where Make includes its
   adapter (makefiles/bindist.inc.mk), before the build data of that file;
   the build without Make (G3-1) does not read it
A2 the recipe: Make's lines with the variables expanded, `$$` as `$`, the
   backslash-newline continuation with the recipe tab removed, `@` stripped
   for the shell and for -n; DIST_FILES from the command line replaces the
   data as in Make
A3 running: each line with /bin/sh -c in the application directory, in
   order, stop at the first failure (exit 1); the environment holds Make's
   exported and command line variables
A4 outside the data: exit 3 (BUILD_IN_DOCKER, a board or application
   without data, building from a distribution); a configuration error: exit 2
A5 the build: cmake_gen.py build in Make's BINDIR (default <app>/bin/<board>,
   or -B / BINDIRBASE), every variable passed on; a failed build makes no
   distribution
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402
sys.path.insert(0, sample.TOOL)
import bindist as B  # noqa: E402
import plan as P  # noqa: E402

APP = os.path.join(sample.RIOTBASE, sample.APP_DIR)
VARS = {"BOARD": sample.BOARD}


class FakeVariables:
    def __init__(self, values):
        self.values = values

    def get(self, name):
        return self.values.get(name, "")

    def words(self, name):
        return self.get(name).split()


class ReadOrderTest(unittest.TestCase):
    """A1."""

    def test_dist_data_before_build_data(self):
        ev = B.evaluate(APP, VARS)
        self.assertEqual(ev.dist_read, ["makefiles/bindist.dist.yaml"])
        self.assertLess(ev.read.index("makefiles/bindist.dist.yaml"),
                        ev.read.index("makefiles/bindist.build.yaml"))
        self.assertEqual(ev.v.words("DIST_FILES"),
                         ["Makefile", "bin/nrf52840dk/abc/*.o",
                          "bin/nrf52840dk/application_bindist/*.o"])

    def test_build_without_make_does_not_read_it(self):
        ev = P.evaluate_application(APP, VARS)
        self.assertNotIn("makefiles/bindist.dist.yaml", ev.read)
        self.assertEqual(ev.v.words("DIST_FILES"), ["Makefile"])

    def test_lazy_like_make(self):
        """DIST_FILES += is recursive: BOARD and BIN_USEMODULE are read when
        the recipe is expanded (a command line BIN_USEMODULE counts)."""
        ev = B.evaluate(APP, dict(VARS, BIN_USEMODULE="abc"))
        self.assertEqual(ev.v.words("DIST_FILES"), ["Makefile", "bin/nrf52840dk/abc/*.o"])


class RecipeTest(unittest.TestCase):
    """A2."""

    VALUES = {"DIST_FILES": "Makefile  bin/b/x/*.o", "BOARD": "b", "APPLICATION": "app",
              "RIOT_VERSION": "1.0", "RIOTBASE": "/riot"}

    def test_lines(self):
        lines = B.recipe(FakeVariables(self.VALUES))
        self.assertEqual(lines, [
            "@mkdir -p bindist",
            "@for i in Makefile  bin/b/x/*.o ; do \\\n\techo Copying $i to bindist. ; \\\n"
            "\tcp -a --parents $i bindist ; \\\n\tdone",
            "@cp -a bin/b/app.bin bindist",
            '@echo "BINDIST_RIOT_VERSION=1.0" > bindist/Makefile.distcheck',
            '@echo "BINDIST_GIT_HEAD=$(git -C /riot describe)" >> bindist/Makefile.distcheck'])

    def test_shown(self):
        self.assertEqual(B.shown("@mkdir -p x"), "mkdir -p x")
        self.assertEqual(B.shown("  -@+ echo"), "echo")
        self.assertEqual(B.shown("echo @x"), "echo @x")

    def test_command_line_dist_files_replaces_the_data(self):
        ev = B.evaluate(APP, dict(VARS, DIST_FILES="README.md"))
        self.assertEqual(ev.v.words("DIST_FILES"), ["README.md"])


class RunTest(unittest.TestCase):
    """A3."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g3-bindist-alg-")
        self.app = sample.prepare(sample.RIOTBASE, self.tmp.name, "default")

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, *extra, variables=None):
        return sample.run(sample.tool_argv(self.app, variables or {}, list(extra)))

    def test_runs_in_the_application_directory(self):
        status, text = self.tool("--no-build")
        self.assertEqual(status, 0, text)
        self.assertTrue(os.path.isfile(os.path.join(self.app, "bindist", "bindist.bin")))
        self.assertFalse(os.path.exists(os.path.join(sample.RIOTBASE, "bindist")))

    def test_stops_at_the_first_failing_line(self):
        with open(os.path.join(self.app, "bindist"), "w", encoding="utf-8") as file:
            file.write("a file, mkdir -p fails\n")
        status, text = self.tool("--no-build")
        self.assertEqual(status, 1)
        self.assertNotIn("Copying", text)
        self.assertIn("mkdir", text)

    def test_environment_of_the_recipe(self):
        ev = B.evaluate(self.app, {"BOARD": sample.BOARD, "RIOT_VERSION": "9.9",
                                   "RIOTBASE": sample.RIOTBASE})
        env = B.recipe_environment(ev.v)
        self.assertEqual(env["RIOT_VERSION"], "9.9")        # command line
        self.assertEqual(env["BOARD"], sample.BOARD)          # exported (vars.build.yaml)
        self.assertEqual(env["BIN_USEMODULE"].split(), ["abc", "application_bindist"])
        # the recipe sees it: the shell reads the environment Make gives
        with mock.patch.object(B, "recipe", lambda v: ['@echo "$BIN_USEMODULE" > env.txt']):
            args, variables = B.parse(["bindist", "--no-build", "-C", self.app,
                                       f"BOARD={sample.BOARD}", f"RIOTBASE={sample.RIOTBASE}"])
            self.assertEqual(B.cmd_bindist(args, variables), 0)
        with open(os.path.join(self.app, "env.txt"), encoding="utf-8") as file:
            self.assertEqual(file.read().split(), ["abc", "application_bindist"])


class ScopeTest(unittest.TestCase):
    """A4."""

    def run_tool(self, app, *variables):
        return subprocess.run([sys.executable, sample.CLI, "bindist", "-n", "-C", app,
                               *variables], capture_output=True, text=True, check=False,
                              cwd=sample.RIOTBASE)

    def test_outside_the_data(self):
        for app, variables in (
                (sample.APP_DIR, [f"BOARD={sample.BOARD}", "BUILD_IN_DOCKER=1"]),
                (sample.APP_DIR, ["BOARD=native64"]),
                ("examples/basic/blinky", [f"BOARD={sample.BOARD}"])):
            with self.subTest(app=app, variables=variables):
                res = self.run_tool(app, *variables)
                self.assertEqual(res.returncode, 3, res.stderr)
                self.assertIn("error:", res.stderr)

    def test_building_from_a_distribution(self):
        with tempfile.TemporaryDirectory(prefix="g3-bindist-scope-") as tmp:
            app = sample.copy_app(sample.RIOTBASE, tmp)
            with open(os.path.join(app, "Makefile.distcheck"), "w", encoding="utf-8") as file:
                file.write("BINDIST_RIOT_VERSION=x\n")
            res = self.run_tool(app, f"BOARD={sample.BOARD}", f"RIOTBASE={sample.RIOTBASE}")
            self.assertEqual(res.returncode, 3, res.stderr)
            self.assertIn("Makefile.distcheck", res.stderr)

    def test_configuration_error(self):
        res = self.run_tool(sample.APP_DIR, "BOARD=no-such-board")
        self.assertEqual(res.returncode, 2, res.stderr)


class BuildStepTest(unittest.TestCase):
    """A5."""

    def calls(self, argv, status=0):
        calls = []
        real_run = subprocess.run

        def fake_run(cmd, **kw):
            if cmd[0] != "/bin/sh" and B.CMAKE_GEN not in cmd:
                return real_run(cmd, **kw)     # the toolchain and git probes
            calls.append((cmd, kw.get("cwd")))
            return subprocess.CompletedProcess(cmd, status if len(calls) == 1 else 0)
        with mock.patch.object(B.subprocess, "run", fake_run), \
                contextlib.redirect_stdout(io.StringIO()):
            args, variables = B.parse(argv)
            code = B.cmd_bindist(args, variables)
        return code, calls

    def test_build_in_makes_bindir(self):
        code, calls = self.calls(["bindist", "-C", APP, f"BOARD={sample.BOARD}", "WERROR=0"])
        self.assertEqual(code, 0)
        build, cwd = calls[0]
        self.assertEqual(build, [sys.executable, B.CMAKE_GEN, "build", "-C", APP, "-B",
                                 os.path.join(APP, "bin", sample.BOARD), "-j", "2",
                                 f"BOARD={sample.BOARD}", "WERROR=0"])
        self.assertIsNone(cwd)
        self.assertEqual([c[0][:2] for c in calls[1:]], [["/bin/sh", "-c"]] * 5)
        self.assertEqual({c[1] for c in calls[1:]}, {APP})

    def test_build_directory_options(self):
        _, calls = self.calls(["bindist", "-C", APP, f"BOARD={sample.BOARD}", "-B", "/x/b"])
        self.assertEqual(calls[0][0][5:7], ["-B", "/x/b"])
        self.assertNotIn("BINDIR=/x/b", calls[0][0])
        _, calls = self.calls(["bindist", "-C", APP, f"BOARD={sample.BOARD}",
                               "BINDIRBASE=/y"])
        self.assertEqual(calls[0][0][5:7], ["-B", f"/y/{sample.BOARD}"])
        self.assertIn("BINDIRBASE=/y", calls[0][0])

    def test_failed_build_makes_no_distribution(self):
        code, calls = self.calls(["bindist", "-C", APP, f"BOARD={sample.BOARD}"], status=1)
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)

    def test_dry_run_and_no_build_do_not_build(self):
        for option in ("-n", "--no-build"):
            with self.subTest(option=option):
                _, calls = self.calls(["bindist", option, "-C", APP, f"BOARD={sample.BOARD}"])
                self.assertFalse(any(B.CMAKE_GEN in c[0] for c in calls))


if __name__ == "__main__":
    unittest.main()
