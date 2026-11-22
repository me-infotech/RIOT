#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D6: the clean data and its Make adapter.

D1 validator: the data file is valid; positive and negative samples
D2 generator: the exact Make text of the adapter
D3 names: Make file, data, adapter; clean data is no build, flash or
   distribution data
D4 adapters up to date (`generate --check`); missing, hand-edited, stale and
   invalid adapters are found (on a copy)
D5 single source: the owner Make file includes its adapter first and assigns
   no variable of its data (detector with positive and negative samples)
D6 scope: no Make file of the repository assigns SCANBUILD_OUTPUTDIR except
   the adapter; every clean data file is read by clean.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402
import cleandata as D  # noqa: E402
import buildeval  # noqa: E402
import clean as C  # noqa: E402

DATA = os.path.join(sample.RIOTBASE, "makefiles", "scan-build.clean.yaml")
OWNER = os.path.join(sample.RIOTBASE, "makefiles", "scan-build.inc.mk")
ADAPTER = os.path.join(sample.RIOTBASE, "makefiles", "scan-build.clean.inc.mk")
DATA_VARS = ("SCANBUILD_OUTPUTDIR",)
ASSIGNS = re.compile(r"^\s*(?:override\s+)?(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*"
                     r"(?:\+|:{1,3}|\?|!)?=", re.M)


def assigned(text: str) -> set:
    """Variables a Make text assigns (recipe lines, starting with a tab, are
    no assignments; nor are target-specific assignments `target: X=`)."""
    lines = [line for line in text.split("\n") if not line.startswith("\t")]
    return {m.group("name") for m in ASSIGNS.finditer("\n".join(lines))}


def doc(rules, schema=3):
    return {"schema": schema, "rules": rules}


class ValidatorTest(unittest.TestCase):
    """D1."""

    def test_data_files(self):
        self.assertEqual(D.all_data(), [DATA])
        self.assertEqual(D.validate(D.R.load_yaml(DATA)), [])

    def test_positive(self):
        for rules in (
                [{"set": {"var": "SCANBUILD_OUTPUTDIR", "value": "scan-build/${BOARD}"}}],
                [{"set": {"var": "X", "value": "${BOARD}", "flavor": "conditional"}}],
                [{"add": {"CLEAN_X": ["a", "b"]}}],
                [{"if": {"equals": {"BOARD": "native64"}},
                  "then": [{"set": {"var": "X", "value": "y"}}]}],
                [{"comment": "only a comment"}]):
            with self.subTest(rules=rules):
                self.assertEqual(D.validate(doc(rules)), [])

    def test_negative(self):
        for document in (
                [],
                {"rules": []},
                doc([], schema=4),
                doc([], schema=1),
                dict(doc([]), extra=1),
                {"schema": 3},
                doc({"set": {}}),
                doc([{"section": "flags"}]),
                doc([{"set": {"var": "X", "value": "y"}, "stand_in": "makefiles/x.inc.mk"}]),
                doc([{"if": {"equals": {"A": "b"}},
                      "then": [{"add": {"X": ["y"]}, "stand_in": "Makefile.include"}]}]),
                doc([{"set": {"var": "X", "value": "$(BOARD)"}}]),
                doc([{"remove": {"X": ["x"]}}]),
                doc([{"add": {"X": ["x"]}, "set": {"var": "Y", "value": "z"}}])):
            with self.subTest(document=document):
                self.assertNotEqual(D.validate(document), [])

    def test_load_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.clean.yaml")
            with open(path, "w", encoding="utf-8") as file:
                file.write("schema: 4\nrules: []\n")
            with self.assertRaisesRegex(ValueError, "schema: must be 3"):
                D.load(path)


class GeneratorTest(unittest.TestCase):
    """D2."""

    def test_adapter_text(self):
        self.assertEqual(D.expected_adapter(DATA), (
            "# Generated from scan-build.clean.yaml by dist/tools/clean/clean.py.\n"
            "# Do not edit: change scan-build.clean.yaml and run `just generate-clean-data`.\n"
            "\n"
            "SCANBUILD_OUTPUTDIR = scan-build/$(BOARD)\n"))

    def test_other_rules(self):
        text = D.make_text([{"set": {"var": "X", "value": "a", "flavor": "conditional"}},
                            {"if": {"equals": {"BOARD": "native64"}},
                             "then": [{"add": {"Y": ["b"]}}]}], "x.clean.yaml")
        self.assertEqual(text.split("\n")[3:], [
            "X ?= a", "", "ifeq ($(BOARD),native64)", "  Y += b", "endif", ""])


class NamesTest(unittest.TestCase):
    """D3."""

    def test_names(self):
        self.assertEqual(D.data_name(OWNER), DATA)
        self.assertEqual(D.adapter_name(DATA), ADAPTER)
        self.assertEqual(D.owner_name(DATA), OWNER)
        self.assertEqual(D.include_line(DATA), "include $(RIOTMAKE)/scan-build.clean.inc.mk")
        self.assertTrue(D.is_data_name(DATA))
        for path in ("makefiles/bindist.build.yaml", "makefiles/vars.flash.yaml",
                     "makefiles/bindist.dist.yaml", ".clean.yaml", "clean.yaml"):
            with self.subTest(path=path):
                self.assertFalse(D.is_data_name(path))
        for path in ("Makefile.include", ADAPTER, "x.mk", ".inc.mk"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    D.data_name(path)
        with self.assertRaises(ValueError):
            D.adapter_name("makefiles/bindist.dist.yaml")

    def test_not_build_flash_or_distribution_data(self):
        self.assertFalse(os.path.exists(buildeval.build_yaml_name(OWNER)))
        self.assertFalse(buildeval.is_flash_adapter(ADAPTER))
        self.assertFalse(DATA.endswith((".flash.yaml", ".dist.yaml", ".build.yaml",
                                        ".inc.yaml")))


class AdaptersTest(unittest.TestCase):
    """D4."""

    def check(self, files=()):
        return subprocess.run([sys.executable, sample.CLI, "generate", "--check", *files],
                              capture_output=True, text=True, check=False)

    def test_up_to_date(self):
        res = self.check()
        self.assertEqual(res.returncode, 0, res.stderr)
        with open(ADAPTER, encoding="utf-8") as file:
            self.assertEqual(file.read(), D.expected_adapter(DATA))

    def test_detects_problems_on_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "scan-build.clean.yaml")
            adapter = os.path.join(tmp, "scan-build.clean.inc.mk")
            shutil.copy(DATA, data)
            self.assertEqual(self.check([data]).returncode, 1)              # missing
            shutil.copy(ADAPTER, adapter)
            self.assertEqual(self.check([data]).returncode, 0)
            with open(adapter, "a", encoding="utf-8") as file:              # hand-edited
                file.write("SCANBUILD_OUTPUTDIR = elsewhere\n")
            res = self.check([data])
            self.assertEqual(res.returncode, 1)
            self.assertIn("is not up to date", res.stderr)
            shutil.copy(ADAPTER, adapter)
            with open(data, "a", encoding="utf-8") as file:                 # stale
                file.write("  - set: {var: X, value: y}\n")
            self.assertEqual(self.check([data]).returncode, 1)
            with open(data, "w", encoding="utf-8") as file:                 # invalid
                file.write("schema: 3\nrules: [{section: x}]\n")
            res = self.check([data])
            self.assertEqual(res.returncode, 1)
            self.assertIn("build data only", res.stderr)
            shutil.copy(DATA, data)                                         # generate
            os.remove(adapter)
            subprocess.run([sys.executable, sample.CLI, "generate", data], check=True,
                           capture_output=True)
            with open(adapter, encoding="utf-8") as file:
                self.assertEqual(file.read(), D.expected_adapter(DATA))


class OwnerTest(unittest.TestCase):
    """D5."""

    def test_owner_includes_adapter_first_and_assigns_no_data_variable(self):
        with open(OWNER, encoding="utf-8") as file:
            text = file.read()
        statements = [line for line in text.split("\n") if line.strip()
                      and not line.lstrip().startswith("#")]
        self.assertEqual(statements[0], D.include_line(DATA))
        self.assertEqual(text.count(D.include_line(DATA)), 1)
        self.assertEqual(assigned(text) & set(DATA_VARS), set())

    def test_detector(self):
        for text in ("SCANBUILD_OUTPUTDIR = x", "SCANBUILD_OUTPUTDIR=x",
                     "  SCANBUILD_OUTPUTDIR := x", "override SCANBUILD_OUTPUTDIR += y",
                     "export SCANBUILD_OUTPUTDIR ?= z"):
            with self.subTest(text=text):
                self.assertIn("SCANBUILD_OUTPUTDIR", assigned(text))
        for text in ("\t$(Q)mkdir -p '$(SCANBUILD_OUTPUTDIR)'", "# SCANBUILD_OUTPUTDIR = x",
                     "X = $(SCANBUILD_OUTPUTDIR)", "-@rm -rf $(SCANBUILD_OUTPUTDIR)"):
            with self.subTest(text=text):
                self.assertNotIn("SCANBUILD_OUTPUTDIR", assigned(text))


class ScopeTest(unittest.TestCase):
    """D6."""

    def test_only_the_adapter_assigns_the_data_variables(self):
        found = []
        for directory, dirs, files in os.walk(sample.RIOTBASE):
            dirs[:] = [d for d in dirs if d not in ("build", "bin") and not d.startswith(".")]
            for name in files:
                if not (name.startswith("Makefile") or name.endswith(".mk")):
                    continue
                path = os.path.join(directory, name)
                try:
                    with open(path, encoding="utf-8") as file:
                        text = file.read()
                except (UnicodeDecodeError, OSError):
                    continue
                if any(v in text and v in assigned(text) for v in DATA_VARS):
                    found.append(os.path.relpath(path, sample.RIOTBASE))
        self.assertEqual(sorted(found), ["makefiles/scan-build.clean.inc.mk"])

    def test_every_clean_data_file_is_read(self):
        owners = [os.path.join(sample.RIOTBASE, owner) for owner, _ in C.CLEAN_OWNERS]
        self.assertEqual(sorted(D.data_name(o) for o in owners), D.all_data())
        for owner in owners:
            with self.subTest(owner=owner):
                self.assertTrue(os.path.isfile(owner))


if __name__ == "__main__":
    unittest.main()
