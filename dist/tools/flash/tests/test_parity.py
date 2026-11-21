#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P5: the flash without Make does what `make flash` does after `all`,
for every application of the scope and every case of the sample (golden
files of the base commit, record_golden.py).

P1 the commands (`flash.py -n` = `make -n -o all flash`): the check of the
   flasher word by word, the flash command as argument vector
P2 the environment of the flasher: the variables its flash action reads
P3 stub tools on PATH: the flasher script, run by the flash without Make,
   calls JLinkExe/openocd/pipx exactly as when Make runs it (arguments, the
   J-Link command file)
P4 live Make with the generated adapters gives the golden commands and stub
   calls (the Make side reads the same data)
P5 the golden files: header, base commit, every case, `## end`

Run: python3 -m unittest discover -s dist/tools/flash/tests -v
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

MAKE = shutil.which("make")
BASE = "5f5b94ff9c"


def all_cases():
    for app, app_dir in sample.APPS.items():
        for case, (variables, jlink_found) in sample.cases(app).items():
            yield app, app_dir, case, variables, jlink_found


class GoldenFilesTest(unittest.TestCase):
    """P5: the reference itself."""

    def test_header_commit_cases_and_end(self):
        for app, app_dir in sample.APPS.items():
            with self.subTest(app=app):
                head, sections = sample.read_golden(sample.golden_path(app))
                self.assertTrue(any(line.startswith(f"# commit: {BASE}") for line in head))
                self.assertIn(f"# flasher environment: {' '.join(sample.ENV_NAMES)}", head)
                expected = [sample.title(case, app_dir, variables, what)
                            for case, (variables, _) in sample.cases(app).items()
                            for what in ("make -n -o all flash", "flasher environment",
                                         "stub calls")]
                self.assertEqual(list(sections), expected)
                for title, body in sections.items():
                    self.assertEqual(body[0], "## exit: 0", title)

    def test_every_supported_programmer_is_a_case(self):
        names = {v.get("PROGRAMMER") for v, _ in sample.CASES.values()}
        self.assertEqual(sorted(n for n in names if n), sorted(sample.SUPPORTED))


class CommandParityTest(unittest.TestCase):
    """P1."""

    def test_flash_commands(self):
        for app, app_dir, case, variables, jlink_found in all_cases():
            with self.subTest(app=app, case=case):
                status, expected = sample.recipe_lines(
                    harness.golden(app, case, variables, "make -n -o all flash"))
                run = harness.Case(app_dir, variables, jlink_found)
                try:
                    code, lines = run.dry_run()
                finally:
                    run.cleanup()
                self.assertEqual((code, status), (0, 0))
                self.assertEqual(len(lines), len(expected), lines)
                self.assertEqual(lines[0], expected[0])               # check_cmd
                self.assertEqual(harness.argv_of(lines[1]), harness.argv_of(expected[1]))


class EnvironmentParityTest(unittest.TestCase):
    """P2."""

    def test_flasher_environment(self):
        for app, app_dir, case, variables, jlink_found in all_cases():
            with self.subTest(app=app, case=case):
                body = harness.golden(app, case, variables, "flasher environment")[1:]
                run = harness.Case(app_dir, variables, jlink_found)
                try:
                    _, lines = run.dry_run()
                    argv = harness.argv_of(lines[-1])
                    flasher = f"flasher {os.path.relpath(argv[0].replace('@RIOTBASE@', sample.RIOTBASE), sample.RIOTBASE)}"
                    self.assertEqual(body[0], flasher + "".join(f" [{a}]" for a in argv[1:]))
                    self.assertEqual(run.environment(), body[1:])
                finally:
                    run.cleanup()


class StubParityTest(unittest.TestCase):
    """P3: hardware stand-ins on PATH."""

    def test_stub_calls(self):
        for app, app_dir, case, variables, jlink_found in all_cases():
            with self.subTest(app=app, case=case):
                expected = harness.golden(app, case, variables, "stub calls")[1:]
                run = harness.Case(app_dir, variables, jlink_found)
                try:
                    res, calls = run.stub_run(tool=True)
                finally:
                    run.cleanup()
                self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                self.assertTrue(calls and calls[0], "a stub was called")
                self.assertEqual(calls, expected)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """P4: GNU Make reading the generated adapters (one Make at a time)."""

    def test_make_commands_and_stub_calls(self):
        for app, app_dir, case, variables, jlink_found in all_cases():
            if app != "hello-world" and case not in ("default", "jlink", "bmp"):
                continue        # the other applications differ only in the image name
            with self.subTest(app=app, case=case):
                _, expected = sample.recipe_lines(
                    harness.golden(app, case, variables, "make -n -o all flash"))
                stubs = harness.golden(app, case, variables, "stub calls")[1:]
                run = harness.Case(app_dir, variables, jlink_found)
                try:
                    res = run.make(["-n", "-o", "all", "flash"])
                    self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                    lines = [line for line in run.norm(res.stdout + res.stderr).split("\n")
                             if line]
                    self.assertEqual(lines, expected)
                    res, calls = run.stub_run(tool=False)
                    self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                    self.assertEqual(calls, stubs)
                finally:
                    run.cleanup()


if __name__ == "__main__":
    unittest.main()
