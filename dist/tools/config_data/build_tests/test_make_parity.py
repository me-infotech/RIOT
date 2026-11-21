#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""B7: with the generated adapters, GNU Make computes the same value for
every variable the build data writes (CFLAGS, INCLUDES, LINKFLAGS, the
linker script, the toolchain, the package settings, the pseudomodules, …)
and exports the same environment to the modules and packages as before the
split. Golden files: recorded on the base commit (record_golden.py), live
Make run now. The other parity checks of the step are the existing ones:
dist/tools/config_data/tests (G0 goldens: info outputs, `make -n -k`) and
dist/tools/cmake_gen/tests (P1-P4: `make -n -k` of the three applications =
the build without Make, live Make with the generated files).

Run: python3 -m unittest discover -s dist/tools/config_data/build_tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# pylint: disable=wrong-import-position
import common as C  # noqa: E402


def golden(app: str) -> list:
    with open(os.path.join(C.GOLDEN, f"{app}__{C.BOARD}.txt"), encoding="utf-8") as file:
        lines = file.read().split("\n")
    assert lines[-2] == "## end", "golden file is truncated"
    return [line for line in lines[:-2] if not line.startswith("# ")]


def names_of(lines: list) -> tuple:
    variables = [line[1:].split("]", 1)[0] for line in lines if line.startswith("[")]
    exported = [line[4:].split("=", 1)[0] for line in lines if line.startswith("ENV ")]
    return variables, exported


class GoldenTest(unittest.TestCase):

    def test_golden_files_name_the_variables_of_the_data(self):
        rules = C.all_rules()
        expected = sorted(C.written_variables(rules) - set(C.VERSION_VARS))
        for app in C.APPS:
            with self.subTest(app=app):
                variables, exported = names_of(golden(app))
                self.assertEqual(variables, expected)
                self.assertGreater(len(exported), 50)
                self.assertLessEqual(set(exported), C.exported_variables(rules))

    def test_golden_header(self):
        with open(os.path.join(C.GOLDEN, f"hello-world__{C.BOARD}.txt"),
                  encoding="utf-8") as file:
            self.assertEqual(file.readline().strip(), f"# commit: {C.BASE}")


@unittest.skipIf(C.MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):

    def test_same_values_and_environment(self):
        for app, app_dir in C.APPS.items():
            expected = golden(app)
            variables, exported = names_of(expected)
            with self.subTest(app=app):
                live = C.make_values(C.RIOTBASE, app_dir, variables, exported)
                self.assertEqual(live, expected)

    def test_a_changed_flag_is_found(self):
        """The comparison sees a difference (detector, negative sample)."""
        expected = golden("hello-world")
        variables, exported = names_of(expected)
        live = C.make_values(C.RIOTBASE, C.APPS["hello-world"], variables, exported)
        changed = [line.replace("-Os", "-O2") for line in live]
        self.assertNotEqual(changed, expected)


if __name__ == "__main__":
    unittest.main()
