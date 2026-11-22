#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P3: test.py gives the golden output of GNU Make (base db4fc1c576).

P1 `test.py <goal> -n` = `make -n <goal>` (the loop of tests.inc.mk:32-34,
   the lines of test/available :37-48), for every case and application
P2 the run: exit status (Make's without the `make: ***` line), output, and
   per script call its path, arguments, working directory and the
   variables the scripts read (TEST_READS: TESTRUNNER_*, PYTHONPATH,
   MAKEFLAGS, MFLAGS, MAKELEVEL, BOARD, USEMODULE, the directories)
P3 BUILD_IN_DOCKER=1 on nrf52840dk runs the scripts here, as Make does
   (case `docker`; decision of 2026-11-22 on T6)
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import tsample as S  # noqa: E402


def check_app(test, app: str, make=False):
    """Compare test.py (or, `make`, live Make) with the golden file."""
    golden = S.read_golden(S.golden_path(app))
    for name, c in S.cases(app).items():
        with tempfile.TemporaryDirectory(prefix="g2b-test-") as tmp:
            run = S.Run(S.RIOTBASE, S.APPS[app], c, tmp)
            got = S.sections_of(run, name, tool=not make)
        for head, body in got.items():
            with test.subTest(app=app, case=name, section=head):
                test.assertEqual(body, golden[head])


class ParityTest(unittest.TestCase):
    """P1-P3 (P3: case `docker`)."""

    def test_hello_world(self):
        check_app(self, "hello-world")

    def test_gnrc_networking(self):
        check_app(self, "gnrc_networking")

    def test_bindist(self):
        check_app(self, "bindist")

    def test_golden_files_complete(self):
        for app in S.APPS:
            golden = S.read_golden(S.golden_path(app))
            self.assertEqual(len(golden), 2 * len(S.cases(app)))


if __name__ == "__main__":
    unittest.main()
