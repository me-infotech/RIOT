#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for features_yaml2mx.py, the generator behind `just generate-features`.

The tests use small in-memory YAML structures and temporary files, so they
neither read nor change files of the repository, except the data-quality
tests at the end, which only read features.yaml.

Run: python3 -m unittest discover -s dist/tools/features_yaml2mx/tests -v
"""
import io
import os
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(TOOL_DIR, "..", "..", ".."))
sys.path.insert(0, TOOL_DIR)

import features_yaml2mx as fy  # noqa: E402  pylint: disable=wrong-import-position

NESTED = {
    "groups": [
        {
            "title": "Outer",
            "help": "outer group",
            "features": [{"name": "feat_b", "help": "b"}],
            "groups": [
                {
                    "title": "Inner",
                    "help": "inner group",
                    "features": [{"name": "feat_a", "help": "a"}],
                }
            ],
        }
    ],
    "features": [{"name": "feat_c", "help": "c"}],
}


def makefile_text(parsed, yaml_path="features.yaml"):
    out = io.StringIO()
    fy.write_makefile(out, yaml_path, parsed)
    return out.getvalue()


class CollectFeaturesTest(unittest.TestCase):
    def test_collects_features_of_nested_groups(self):
        self.assertCountEqual(fy.collect_features(NESTED), ["feat_a", "feat_b", "feat_c"])

    def test_empty_document_has_no_features(self):
        self.assertEqual(fy.collect_features({}), [])


class WriteMakefileTest(unittest.TestCase):
    def test_features_are_sorted(self):
        lines = makefile_text(NESTED).splitlines()
        body = [line.strip(" \\") for line in lines if line.startswith("    feat_")]
        self.assertEqual(body, ["feat_a", "feat_b", "feat_c"])

    def test_variable_is_terminated(self):
        text = makefile_text(NESTED)
        self.assertIn("FEATURES_EXISTING := \\\n", text)
        self.assertTrue(text.endswith("    #\n"))

    def test_output_does_not_depend_on_input_order(self):
        reordered = {"features": list(reversed(NESTED["features"])),
                     "groups": NESTED["groups"]}
        self.assertEqual(makefile_text(NESTED), makefile_text(reordered))

    def test_header_names_source_file(self):
        self.assertIn("auto-generated from my.yaml", makefile_text(NESTED, "my.yaml"))

    def test_header_points_to_just_not_make(self):
        text = makefile_text(NESTED)
        self.assertIn("run `just generate-features`", text)
        self.assertNotIn("make generate-features", text)


class WriteMdfileTest(unittest.TestCase):
    def test_header_points_to_just_not_make(self):
        out = io.StringIO()
        fy.write_mdfile(out, "features.yaml", NESTED)
        self.assertIn("run `just generate-features`", out.getvalue())
        self.assertNotIn("make generate-features", out.getvalue())


class ConvertFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        self.yaml_path = os.path.join(self.tmp.name, "features.yaml")
        with open(self.yaml_path, "w", encoding="utf-8") as file:
            yaml.safe_dump(NESTED, file)
        self.mk_path = os.path.join(self.tmp.name, "out.inc.mk")

    def read_mk(self):
        with open(self.mk_path, encoding="utf-8") as file:
            return file.read()

    def test_conversion_is_idempotent(self):
        fy.convert_features(self.yaml_path, self.mk_path, None)
        first = self.read_mk()
        fy.convert_features(self.yaml_path, self.mk_path, None)
        self.assertEqual(first, self.read_mk())

    def test_no_markdown_written_when_not_requested(self):
        fy.convert_features(self.yaml_path, self.mk_path, None)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["features.yaml", "out.inc.mk"])


class RepositoryDataTest(unittest.TestCase):
    """Read-only checks of the real input and output of `just generate-features`."""

    @classmethod
    def setUpClass(cls):
        cls.yaml_path = os.path.join(RIOTBASE, "features.yaml")
        with open(cls.yaml_path, "rb") as file:
            cls.parsed = yaml.safe_load(file)

    def test_feature_names_are_unique(self):
        names = fy.collect_features(self.parsed)
        duplicates = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(duplicates, [])

    def test_committed_makefile_is_up_to_date(self):
        committed = os.path.join(RIOTBASE, "makefiles", "features_existing.inc.mk")
        with open(committed, encoding="utf-8") as file:
            expected = file.read()
        self.assertEqual(makefile_text(self.parsed, "features.yaml"), expected,
                         "run `just generate-features` after changing features.yaml")


if __name__ == "__main__":
    unittest.main()
