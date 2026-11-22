#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: test.py depends on Make in no way (the detectors of step G2B-1,
dist/tools/term/tests/test_no_make.py).

The proof is for test.py itself: the test scripts it runs may call make
(dist/pythonlibs/testrunner/spawn.py runs `make cleanterm` and `make reset`,
decision T2); here the scripts are the recorder, which does not.

N1 audit-hook trace of test.py for every application (dry run, environment,
   a run of the recorder, test/available): no Make file is opened, no make
   process is started
N2 `just test` / `just test-available` -> test.py -> the recorder, with a
   stub `make`/`gmake` first on PATH that is never called
N3 static check: no module of dist/tools/test starts a process itself
   (term.py's run and shell do) or names make as a program
N4 the just recipes have no make call
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
import tsample as S  # noqa: E402


def term_test_module(name: str):
    path = os.path.join(S.TOOL, "..", "term", "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"term_tests_{name}", path)
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
    return module


TN = term_test_module("test_no_make")
JUST = shutil.which("just")


class Traced(TN.Traced):
    """term's tracer with the recorder and the stub git of this step."""

    def __init__(self):
        super().__init__()
        self.run_ = S.Run(S.RIOTBASE, S.APPS["hello-world"], S.case(), self.tmp.name)
        self.env["PATH"] = self.bin + os.pathsep + self.run_.stubs + os.pathsep + \
            self.env["PATH"]
        self.env["G2B_TEST_LOG"] = self.run_.log

    def recorded(self):
        return self.lines(self.run_.log)


class TraceTest(unittest.TestCase):
    """N1."""

    RUNS = ((["test", "-n"], []), (["test", "--print-env"], ["QUIET=0"]),
            (["test"], ["TESTS=@REC@ @REC@"]), (["test/available"], ["TESTS=@REC@"]))

    def test_opens_no_make_file_and_starts_no_make(self):
        for app_dir in S.APPS.values():
            for options, variables in self.RUNS:
                t = Traced()
                try:
                    res = t.run([sys.executable, S.CLI, *options, "-C", app_dir,
                                 f"BOARD={S.BOARD}",
                                 *[t.run_.value(v) for v in variables]])
                    events = t.events()
                    with self.subTest(app=app_dir, options=options):
                        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                        self.assertTrue(any(e[0] == "run" for e in events))   # tracer works
                        if options == ["test"]:
                            self.assertTrue(t.recorded())                    # scripts ran
                        self.assertEqual(TN.make_events(events), ([], []))
                        self.assertEqual(t.lines(t.make_log), [])
                finally:
                    t.cleanup()


@unittest.skipIf(JUST is None, "just is not installed")
class ChainTest(unittest.TestCase):
    """N2."""

    def test_just_recipes_without_make(self):
        for recipe in ("test", "test-available"):
            t = Traced()
            try:
                res = t.run([JUST, recipe, S.APPS["hello-world"], S.BOARD,
                             t.run_.value("TESTS=@REC@ @REC@")])
                with self.subTest(recipe=recipe):
                    self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                    calls = [l for l in t.recorded() if l.startswith("script ")]
                    self.assertEqual(len(calls), 2 if recipe == "test" else 0)
                    self.assertEqual(TN.make_events(t.events()), ([], []))
                    self.assertEqual(t.lines(t.make_log), [])
            finally:
                t.cleanup()


class StaticTest(unittest.TestCase):
    """N3."""

    def test_no_process_and_no_make(self):
        for name in sorted(f for f in os.listdir(S.TOOL) if f.endswith(".py")):
            with open(os.path.join(S.TOOL, name), encoding="utf-8") as file:
                process, makes = TN.StaticTest.problems(file.read())
            with self.subTest(module=name):
                self.assertEqual(process, [])
                self.assertEqual(makes, [])


@unittest.skipIf(JUST is None, "just is not installed")
class RecipeTest(unittest.TestCase):
    """N4."""

    def test_recipes_have_no_make_call(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True,
                             text=True, check=True)
        recipes = json.loads(res.stdout)["recipes"]
        for name in ("test", "test-available"):
            body = json.dumps(recipes[name]["body"])
            with self.subTest(recipe=name):
                self.assertIn("dist/tools/test/test.py", body)
                self.assertEqual(TN.MAKE_CALL.findall(body), [])


if __name__ == "__main__":
    unittest.main()
