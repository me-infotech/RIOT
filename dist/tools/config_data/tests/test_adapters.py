#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C5: the checked-in Make files are exactly what the generator writes from
the YAML (CI check), the just recipe regenerates them, and
C8: generating and validating the data needs no Make.

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOL)

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import rules as R  # noqa: E402

CLI = os.path.join(TOOL, "config_data.py")
JUST = shutil.which("just")
RECIPE = "generate-config-data"
DATA_MODULES = ("rules.py", "schema.py", "generate.py", "translate.py")


def run(args, **kwargs):
    return subprocess.run([sys.executable, CLI] + args, capture_output=True, text=True,
                          check=False, **kwargs)


class UpToDateTest(unittest.TestCase):

    def test_checked_in_make_files_are_up_to_date(self):
        result = run(["generate", "--check"])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_yaml_files_are_exactly_the_scope(self):
        scope = config_data.load_scope()
        expected = sorted(os.path.join(R.RIOTBASE, R.yaml_name(p))
                          for p in config_data.converted_files(scope))
        self.assertEqual(config_data.all_yaml(), expected)

    def test_generated_files_carry_the_header(self):
        for path in config_data.converted_files(config_data.load_scope()):
            with self.subTest(path=path):
                with open(os.path.join(R.RIOTBASE, path), encoding="utf-8") as file:
                    first = file.readline()
                self.assertEqual(first, f"# Generated from {os.path.basename(R.yaml_name(path))}"
                                        " by dist/tools/config_data/config_data.py.\n")


class CheckDetectsStaleFilesTest(unittest.TestCase):
    """The CI check on a copy: it must fail for each kind of drift."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        self.yaml = os.path.join(self.tmp.name, "deps.yaml")
        self.make = os.path.join(self.tmp.name, "Makefile.dep")
        source = os.path.join(R.RIOTBASE, "sys", "ztimer")
        shutil.copy(os.path.join(source, "deps.yaml"), self.yaml)
        shutil.copy(os.path.join(source, "Makefile.dep"), self.make)

    def edit(self, path, old, new):
        with open(path, encoding="utf-8") as file:
            text = file.read()
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text.replace(old, new, 1))

    def test_copy_is_up_to_date(self):
        self.assertEqual(run(["generate", "--check", self.yaml]).returncode, 0)

    def test_yaml_changed_without_regenerating(self):
        self.edit(self.yaml, "ztimer_periph_rtt]", "ztimer_periph_rtc]")
        result = run(["generate", "--check", self.yaml])
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not up to date with deps.yaml", result.stderr)
        self.assertIn("just generate-config-data", result.stderr)
        # regenerating repairs it
        self.assertEqual(run(["generate", self.yaml]).returncode, 0)
        self.assertEqual(run(["generate", "--check", self.yaml]).returncode, 0)

    def test_make_file_edited_by_hand(self):
        self.edit(self.make, "USEMODULE += ztimer_periph_rtt", "USEMODULE += ztimer_periph_rtc")
        self.assertEqual(run(["generate", "--check", self.yaml]).returncode, 1)

    def test_make_file_missing(self):
        os.remove(self.make)
        self.assertEqual(run(["generate", "--check", self.yaml]).returncode, 1)

    def test_invalid_yaml_is_reported_and_nothing_written(self):
        self.edit(self.yaml, "match: [ztimer_periph_rtt]", "match: ['$(X)']")
        before = os.path.getmtime(self.make)
        result = run(["generate", self.yaml])
        self.assertEqual(result.returncode, 1)
        self.assertIn("'$(X)' is not a pattern", result.stderr)
        self.assertEqual(os.path.getmtime(self.make), before)
        self.assertEqual(run(["validate", self.yaml]).returncode, 1)


class FileNameTest(unittest.TestCase):

    def test_pairs(self):
        for make, data in (("sys/Makefile.dep", "sys/deps.yaml"),
                           ("cpu/nrf52/Makefile.nrf802154.dep", "cpu/nrf52/nrf802154.deps.yaml"),
                           ("Makefile.features", "provides.yaml"),
                           ("boards/x/Makefile.board.features", "boards/x/board.provides.yaml"),
                           ("boards/x/Makefile.default", "boards/x/default.yaml"),
                           ("makefiles/stdio.inc.mk", "makefiles/stdio.inc.yaml"),
                           ("examples/basic/hello-world/Makefile",
                            "examples/basic/hello-world/riot-app.yaml")):
            with self.subTest(make=make):
                self.assertEqual(R.yaml_name(make), data)
                self.assertEqual(R.make_name(data), make)
                self.assertTrue(R.is_yaml_name(data))

    def test_other_names_are_rejected(self):
        for name in ("Makefile.include", "Makefile.ci", "features.yaml", "x.yaml", ".inc.yaml"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    R.yaml_name(name) if name.startswith("Makefile") else R.make_name(name)
        self.assertFalse(R.is_yaml_name("features.yaml"))


@unittest.skipIf(JUST is None, "just is not installed")
class JustRecipeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        result = subprocess.run([JUST, "--justfile", os.path.join(R.RIOTBASE, "justfile"),
                                 "--dump", "--dump-format", "json"],
                                capture_output=True, text=True, check=True)
        cls.recipe = json.loads(result.stdout)["recipes"][RECIPE]

    def test_recipe_runs_the_generator(self):
        result = subprocess.run([JUST, "--justfile", os.path.join(R.RIOTBASE, "justfile"),
                                 "--dry-run", RECIPE], capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), "./dist/tools/config_data/config_data.py generate")

    def test_recipe_is_public_without_dependencies_or_parameters(self):
        self.assertFalse(self.recipe["private"])
        self.assertEqual(self.recipe["dependencies"], [])
        self.assertEqual(self.recipe["parameters"], [])


class NoMakeTest(unittest.TestCase):
    """C8: the data, the generator and the check do not depend on Make."""

    def test_data_modules_start_no_process(self):
        for name in DATA_MODULES:
            with self.subTest(module=name):
                with open(os.path.join(TOOL, name), encoding="utf-8") as file:
                    text = file.read()
                self.assertIsNone(re.search(r"\b(subprocess|os\.system|os\.popen)\b", text))

    def test_generate_and_validate_without_make_on_path(self):
        with tempfile.TemporaryDirectory() as bin_dir:
            for tool in ("git",):
                if shutil.which(tool):
                    os.symlink(shutil.which(tool), os.path.join(bin_dir, tool))
            env = {"PATH": bin_dir, "HOME": os.environ.get("HOME", "/")}
            self.assertIsNone(shutil.which("make", path=bin_dir))
            for args in (["generate", "--check"], ["validate"]):
                with self.subTest(args=args):
                    result = run(args, env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
