#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P4: debug.py against the golden output of GNU Make (base d04191b950).

P1 the commands of `-n` are Make's (`make -n <goal>`), the hint of a program
   that is not set included
P2 the run with the real scripts of dist/tools and the stub tools: the
   output, the exit status, every stub call with its arguments and the
   variables of DEBUG_READS (the debugger's environment), the calls of
   ttys.py and the servers left running (jlink: JLinkGDBServer, as Make)
P3 a configuration error is Make's `$(error)` text with exit 2 (an unknown
   programmer: FLASHFILE not defined), without `make: ***`; requests outside
   the data exit 3 with a message (pyocd, DEBUGDEPS: PyCortexMDebug, EMULATE,
   setsid on macOS; native64), where Make builds, fetches or fails
P4 the golden files: header (commit, generator), one section per case and
   kind, `## end`
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import debug_sample as S  # noqa: E402

BASE = "d04191b950"


def golden(app: str, name: str, what: str) -> tuple:
    c = S.CASES[name]
    what = f"make -n {c['goal']}" if what == "dry-run" else what
    sections = S.TS.read_golden(S.golden_path(app))[1]
    return S.TS.status_and_lines(sections[S.title(name, S.APPS[app], c, what)])


def check_case(test, app: str, name: str, c: dict, argv_of):
    """Compare one case: argv_of(run, options) gives the command (debug.py or
    live Make)."""
    with tempfile.TemporaryDirectory(prefix="g2b-debug-") as tmp:
        run = S.Run(S.RIOTBASE, S.APPS[app], c, tmp)
        status, out, err = run.capture(argv_of(run, "-n"))
        if c["outside"]:
            return status, run.norm(err)
        g_status, g_lines = golden(app, name, "dry-run")
        if c["error"]:                                   # Make's $(error): exit 2
            with test.subTest(app=app, case=name, what="error"):
                test.assertEqual((status, g_status), (2, 2))
                test.assertTrue(any(l.endswith(f"*** {c['error']}.  Stop.") for l in g_lines))
                test.assertIn(f"error: {c['error']}", err)
                test.assertNotIn("make: ***", err)
            return None
        with test.subTest(app=app, case=name, what="-n"):
            test.assertEqual(status, g_status, err)
            test.assertEqual([l for l in run.norm(out).split("\n") if l], g_lines)
        g_status, g_lines = golden(app, name, "run")
        status, lines, stubs = run.run(argv_of(run, None))
        with test.subTest(app=app, case=name, what="run"):
            test.assertEqual(status, g_status)
            test.assertEqual(lines + stubs, g_lines)
            test.assertFalse(any("make: ***" in l or "make[" in l for l in lines))
    return None


def tool(run, option):
    return run.tool_argv([option] if option else [])


class ParityTest(unittest.TestCase):
    """P1-P3."""

    def check(self, app: str):
        for name, c in S.cases(app).items():
            result = check_case(self, app, name, c, tool)
            if c["outside"]:
                with self.subTest(app=app, case=name, what="outside"):      # P3
                    status, err = result
                    self.assertEqual(status, 3, err)
                    self.assertTrue(err.startswith("error: ") and "make" in err, err)

    def test_hello_world(self):
        self.check("hello-world")

    def test_gnrc_networking(self):
        self.check("gnrc_networking")

    def test_bindist(self):
        self.check("bindist")


class GoldenFilesTest(unittest.TestCase):
    """P4."""

    def test_headers_and_sections(self):
        for app in S.APPS:
            with self.subTest(app=app):
                head, sections = S.TS.read_golden(S.golden_path(app))
                commit = [h for h in head if h.startswith("# commit: ")]
                self.assertTrue(commit and commit[0][len("# commit: "):].startswith(BASE))
                self.assertIn("# generator: dist/tools/debug/tests/record_golden.py", head)
                cases = [c for c in S.cases(app).values() if c["record"]]
                self.assertEqual(len(sections),
                                 sum(1 if c["outside"] or c["error"] else 2 for c in cases))


if __name__ == "__main__":
    unittest.main()
