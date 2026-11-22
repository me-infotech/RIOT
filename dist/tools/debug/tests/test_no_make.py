#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: the debugger without Make depends on Make in no way (the
detectors of step G2B-1, dist/tools/term/tests/test_no_make.py).

N1 audit-hook trace of debug.py for every application and goal (dry run,
   environment, a run with the stub tools): no Make file is opened, no make
   process is started
N2 `just debug|debug-server|debug-client` -> debug.py -> the scripts, with a
   stub `make`/`gmake` first on PATH that is never called
N3 static check: no module of dist/tools/debug starts a process itself
   (term.py's run does) or names make as a program
N4 the just recipes have no make call
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import debug_sample as S  # noqa: E402

TN = S.term_test_module("test_no_make")
JUST = shutil.which("just")


class Traced(TN.Traced):
    """term's tracer with the stub tools of this step and the image."""

    def __init__(self):
        super().__init__()
        root = self.tmp.name
        self.dbg = os.path.join(root, "dbg")
        os.makedirs(self.dbg)
        dirs = S.make_stubs(os.path.join(root, "dstubs"), S.ALL_TOOLS)
        self.env["PATH"] = self.bin + os.pathsep + S.stub_path(dirs)
        self.env["G2B_DBG_DIR"] = self.dbg
        bindir = os.path.join(self.bindirbase, S.BOARD)
        os.makedirs(bindir)
        for name in S.APP_NAMES.values():
            with open(os.path.join(bindir, name + ".elf"), "w", encoding="utf-8") as file:
                file.write("image\n")

    def stop(self):
        open(os.path.join(self.dbg, "stop"), "w", encoding="utf-8").close()


class TraceTest(unittest.TestCase):
    """N1."""

    RUNS = ((["debug", "-n"], ["PROGRAMMER=jlink"]),
            (["debug-server", "--print-env"], ["MOST_RECENT_PORT=1"]),
            (["debug-client"], ["PROGRAMMER=openocd"]),
            (["debug"], ["PROGRAMMER=bmp"]))

    def test_debug_opens_no_make_file_and_starts_no_make(self):
        for app_dir in S.APPS.values():
            for options, variables in self.RUNS:
                t = Traced()
                try:
                    res = t.run([sys.executable, S.CLI, *options, "-C", app_dir,
                                 f"BOARD={S.BOARD}", f"BINDIRBASE={t.bindirbase}", *variables])
                    events = t.events()
                    with self.subTest(app=app_dir, options=options):
                        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                        self.assertTrue(any(e[0] == "run" for e in events))   # tracer works
                        if len(options) == 1:                                  # stubs ran
                            self.assertTrue([f for f in os.listdir(t.dbg) if f.endswith(".log")])
                        self.assertEqual(TN.make_events(events), ([], []))
                        self.assertEqual(t.lines(t.make_log), [])
                finally:
                    t.stop()
                    t.cleanup()


@unittest.skipIf(JUST is None, "just is not installed")
class ChainTest(unittest.TestCase):
    """N2."""

    def test_just_recipes_without_make(self):
        for recipe, variables in (("debug", ["PROGRAMMER=openocd"]),
                                  ("debug-client", ["PROGRAMMER=openocd"]),
                                  ("debug-server", ["PROGRAMMER=bmp"])):
            t = Traced()
            try:
                res = t.run([JUST, recipe, S.APPS["hello-world"], S.BOARD,
                             f"BINDIRBASE={t.bindirbase}", *variables])
                with self.subTest(recipe=recipe):
                    if recipe == "debug-server":       # bmp: Make's hint, exit 2
                        self.assertNotEqual(res.returncode, 0)
                        self.assertIn("$(DEBUGSERVER) is not set", res.stdout)
                    else:
                        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                        self.assertTrue(os.path.exists(os.path.join(t.dbg,
                                                                    "arm-none-eabi-gdb.log")))
                    self.assertEqual(TN.make_events(t.events()), ([], []))
                    self.assertEqual(t.lines(t.make_log), [])
            finally:
                t.stop()
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
        for name in S.GOALS:
            body = json.dumps(recipes[name]["body"])
            with self.subTest(recipe=name):
                self.assertIn("dist/tools/debug/debug.py", body)
                self.assertEqual(TN.MAKE_CALL.findall(body), [])


if __name__ == "__main__":
    unittest.main()
