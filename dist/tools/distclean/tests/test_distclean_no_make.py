#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: `distclean` without Make depends on Make in no way. The detectors
are those of step G2C-1 (dist/tools/clean/tests/test_no_make.py: audit-hook
tracer, stub make, static check, recipe check), loaded from there.

N1 audit-hook trace of `clean.py distclean -n` and `clean.py distclean` for
   every case of the sample on a tree with stand-in build products and
   package sources: no Make file opened, no make process started (positive
   probe of both detectors); the processes started are rm (git for
   in-source packages, the toolchain probes of the build data) only
N2 `just distclean` with a stub `make`/`gmake` first on PATH that is never
   called: the products and package sources are gone
N3 static check: the code of distclean (clean.py) names no make program;
   the step adds no other module
N4 the just recipe `distclean` has no make call
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402
import sample as S  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "clean_no_make", os.path.join(D.CLEAN_TESTS, "test_no_make.py"))
N = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(N)

JUST = shutil.which("just")
SOURCES = ("pkg/cmsis/CMSIS/x.h", "pkg/mpaland-printf/printf.c")


def traced(app="hello-world"):
    """The G2C-1 trace set-up plus package sources in its BUILD_DIR."""
    t = N.Traced(app)
    build = os.path.join(t.tmp.name, "build")
    for name in SOURCES:
        S._touch(os.path.join(build, name), 0)  # pylint: disable=protected-access
    return t, build


class TraceTest(unittest.TestCase):
    """N1."""

    def test_distclean_opens_no_make_file_and_starts_no_make(self):
        for case, (app, variables) in D.CASES.items():
            for option in ("-n", None):
                t, build = traced(app)
                try:
                    values = dict({"BUILD_DIR": build}, **S.real(variables, t.tmp.name))
                    res = t.run(D.tool_argv(t.app, values, [option] if option else []))
                    events = t.events()
                    with self.subTest(case=case, option=option):
                        self.assertEqual(res.returncode, 0, res.stderr)
                        self.assertTrue(any(e[0] == "start"
                                            and any(a.endswith("clean.py") for a in e[1])
                                            for e in events))
                        self.assertEqual(N.make_events(events), ([], []))
                        self.assertEqual(t.make_calls(), [])
                        programs = {os.path.basename(e[1][0]) for e in events if e[0] == "run"}
                        self.assertLessEqual(programs - {"rm", "git", "arm-none-eabi-gcc"},
                                             set(), programs)
                        if option is None and case in ("hello-world", "gnrc_networking",
                                                       "bindist", "docker"):
                            self.assertIn("rm", programs)
                            self.assertFalse(os.path.exists(os.path.join(t.app, "bin")))
                            for name in SOURCES:
                                self.assertFalse(os.path.exists(os.path.join(build, name)))
                        if option == "-n":
                            self.assertTrue(os.path.isdir(os.path.join(t.app, "bin")))
                finally:
                    t.cleanup()

    def test_probes_of_the_detectors(self):
        t, _ = traced()
        try:
            script = ("import subprocess; open('Makefile.include').read(); "
                      "subprocess.run(['make', '--version'])")
            t.run([sys.executable, "-c", script])
            opened, started = N.make_events(t.events())
            self.assertEqual(opened, ["Makefile.include"])
            self.assertEqual(started, [["make", "--version"]])
            self.assertEqual(len(t.make_calls()), 1)
        finally:
            t.cleanup()


@unittest.skipIf(JUST is None, "just is not installed")
class ChainTest(unittest.TestCase):
    """N2."""

    def test_just_distclean_without_make(self):
        t, build = traced()
        try:
            res = t.run([JUST, "distclean", t.app, D.BOARD, f"RIOTBASE={D.RIOTBASE}",
                         f"BUILD_DIR={build}"])
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse(os.path.exists(os.path.join(t.app, "bin")))
            for name in SOURCES:
                self.assertFalse(os.path.exists(os.path.join(build, name)), name)
            self.assertTrue(os.path.isfile(os.path.join(t.app, "Makefile")))
            self.assertEqual(N.make_events(t.events()), ([], []))
            self.assertEqual(t.make_calls(), [])
        finally:
            t.cleanup()


class StaticTest(unittest.TestCase):
    """N3."""

    def test_no_new_module_and_no_make(self):
        tool = os.path.dirname(D.CLI)
        self.assertEqual(sorted(f for f in os.listdir(tool) if f.endswith(".py")),
                         ["clean.py", "cleandata.py"])
        with open(D.CLI, encoding="utf-8") as file:
            _, makes = N.StaticTest.problems(file.read())
        self.assertEqual(makes, [])
        self.assertEqual(sorted(f for f in os.listdir(os.path.dirname(HERE))), ["tests"])

    def test_probe(self):
        _, makes = N.StaticTest.problems("import subprocess\nsubprocess.run(['gmake'])\n")
        self.assertEqual(makes, ["gmake"])


@unittest.skipIf(JUST is None, "just is not installed")
class RecipeTest(unittest.TestCase):
    """N4."""

    def test_recipe_has_no_make_call(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(D.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True,
                             text=True, check=True)
        body = json.dumps(json.loads(res.stdout)["recipes"]["distclean"]["body"])
        self.assertIn("dist/tools/clean/clean.py distclean", body)
        self.assertEqual(N.MAKE_CALL.findall(body), [])
        self.assertTrue(N.MAKE_CALL.findall('"make" -C pkg distclean'))


if __name__ == "__main__":
    unittest.main()
