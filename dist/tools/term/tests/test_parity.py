#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P5: the terminal without Make does what GNU Make did (golden files of
the base commit, sample.py), for every application and case.

P1 `term.py -n` prints the commands of `make -n term` (`cleanterm`): the
   check_cmd line and the terminal command, character by character (with
   Make's blanks of empty variables)
P2 the terminal is called with the same arguments and the same variables
   (TERM_READS) as by `make term`; ttys.py is asked the same question
P3 the command line is echoed as Make echoes it
P4 exit status: 0, 2 for a missing or failing terminal and for Make's
   `$(error)` (the message of the recipe or the data, without Make's
   `make: ***` line)
P5 the header of each golden file names the base commit and the stubs
"""

import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import harness  # noqa: E402
import sample  # noqa: E402

BASE = "481caa4b65"


def make_message(lines: list) -> str:
    """The text of Make's `$(error)`: `file:line: *** TEXT.  Stop.`"""
    for line in lines:
        if "*** " in line and line.endswith(".  Stop."):
            return line.split("*** ", 1)[1][:-len(".  Stop.")]
    raise AssertionError(f"no Make error in {lines}")


class ParityTest(unittest.TestCase):
    """P1-P4."""

    def check(self, app: str):
        for name, c in sample.cases(app).items():
            if not c["path"] and shutil.which("picocom", path="/usr/local/bin:/usr/bin:/bin"):
                continue                        # a real picocom would be found
            case = harness.Case(sample.APPS[app], c)
            try:
                g_status, g_lines = harness.golden(app, name, "dry-run")
                dry = case.dry_run()
                t_status, t_lines = harness.golden(app, name, "terminal call")
                status, lines = case.terminal_call(dry)
                with self.subTest(app=app, case=name):
                    self.assertEqual(dry[0], g_status, dry[2])
                    self.assertEqual(status, t_status)
                    if g_status == 0:
                        self.assertEqual(dry[1], g_lines)                       # P1
                        self.assertEqual(lines, t_lines)                        # P2-P4
                    else:                                                       # P4
                        self.assertIn(make_message(g_lines), dry[2])
                        self.assertIn(make_message([l[5:] for l in t_lines]), "\n".join(lines))
                        self.assertNotIn("make: ***", dry[2])
            finally:
                case.cleanup()

    def test_hello_world(self):
        self.check("hello-world")

    def test_gnrc_networking(self):
        self.check("gnrc_networking")

    def test_bindist(self):
        self.check("bindist")


class GoldenFilesTest(unittest.TestCase):
    """P5."""

    def test_headers_and_sections(self):
        for app in sample.APPS:
            with self.subTest(app=app):
                head, sections = sample.read_golden(sample.golden_path(app))
                commit = [h for h in head if h.startswith("# commit: ")]
                self.assertTrue(commit and commit[0][len("# commit: "):].startswith(BASE))
                self.assertTrue(any(sample.DATE in h for h in head))
                self.assertEqual(len(sections), 2 * len(sample.cases(app)))


if __name__ == "__main__":
    unittest.main()
