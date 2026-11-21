#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D6: the distribution data and its Make adapters.

D1 validator: the data file is valid; positive and negative samples
D2 generator: the exact Make text of the adapter
D3 names: Make file, data, adapter; distribution data is no build or flash data
D4 adapters up to date (`generate --check`); missing, hand-edited, stale and
   invalid adapters are found (on a copy)
D5 single source: the owner Make file includes its adapter first and assigns
   no variable of its data (detector with positive and negative samples)
D6 scope: no Make file of the repository assigns DIST_FILES except the
   adapter and the application Makefiles generated from riot-app.yaml
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
sys.path.insert(0, sample.TOOL)
import distdata as D  # noqa: E402
import buildeval  # noqa: E402

DATA = os.path.join(sample.RIOTBASE, "makefiles", "bindist.dist.yaml")
OWNER = os.path.join(sample.RIOTBASE, "makefiles", "bindist.inc.mk")
ADAPTER = os.path.join(sample.RIOTBASE, "makefiles", "bindist.dist.inc.mk")
DATA_VARS = ("DIST_FILES",)
ASSIGNS = re.compile(r"^\s*(?:override\s+)?(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*"
                     r"(?:\+|:{1,3}|\?|!)?=", re.M)


def assigned(text: str) -> set:
    """Variables a Make text assigns (recipe lines, starting with a tab, are
    no assignments)."""
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
                [{"add": {"DIST_FILES": ["Makefile"]}}],
                [{"add": {"DIST_FILES": [{"select": {"var": "BIN_USEMODULE",
                                                     "pattern": {"from": "%", "to": "b/%/*.o"}}}]}}],
                [{"set": {"var": "X", "value": "${BOARD}", "flavor": "conditional"}}],
                [{"if": {"has": {"var": "USEMODULE", "match": ["abc"]}},
                  "then": [{"add": {"DIST_FILES": ["abc.txt"]}}]}],
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
                doc({"add": {}}),
                doc([{"section": "files"}]),
                doc([{"add": {"DIST_FILES": ["x"]}, "stand_in": "makefiles/bindist.inc.mk"}]),
                doc([{"if": {"has": {"var": "A", "match": ["b"]}},
                      "then": [{"add": {"X": ["y"]}, "stand_in": "Makefile.include"}]}]),
                doc([{"add": {"DIST_FILES": ["$(BOARD)"]}}]),
                doc([{"copy": {"DIST_FILES": ["x"]}}]),
                doc([{"add": {"DIST_FILES": ["x"]}, "set": {"var": "Y", "value": "z"}}])):
            with self.subTest(document=document):
                self.assertNotEqual(D.validate(document), [])

    def test_load_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.dist.yaml")
            with open(path, "w", encoding="utf-8") as file:
                file.write("schema: 4\nrules: []\n")
            with self.assertRaisesRegex(ValueError, "schema: must be 3"):
                D.load(path)


class GeneratorTest(unittest.TestCase):
    """D2."""

    def test_adapter_text(self):
        self.assertEqual(D.expected_adapter(DATA), (
            "# Generated from bindist.dist.yaml by dist/tools/bindist/bindist.py.\n"
            "# Do not edit: change bindist.dist.yaml and run `just generate-dist-data`.\n"
            "\n"
            "# the objects of the binary modules, where Make's recipe finds them\n"
            "# (bin/<BOARD>: Make's default BINDIR, relative to the application)\n"
            "DIST_FILES += $(patsubst %,bin/$(BOARD)/%/*.o,$(BIN_USEMODULE))\n"))

    def test_other_rules(self):
        text = D.make_text([{"set": {"var": "X", "value": "a", "flavor": "conditional"}},
                            {"if": {"has": {"var": "USEMODULE", "match": ["abc"]}},
                             "then": [{"add": {"DIST_FILES": ["abc.txt"]}}]}], "x.dist.yaml")
        self.assertEqual(text.split("\n")[3:], [
            "X ?= a", "", "ifneq (,$(filter abc,$(USEMODULE)))",
            "  DIST_FILES += abc.txt", "endif", ""])


class NamesTest(unittest.TestCase):
    """D3."""

    def test_names(self):
        self.assertEqual(D.data_name(OWNER), DATA)
        self.assertEqual(D.adapter_name(DATA), ADAPTER)
        self.assertEqual(D.owner_name(DATA), OWNER)
        self.assertEqual(D.include_line(DATA), "include $(RIOTMAKE)/bindist.dist.inc.mk")
        self.assertTrue(D.is_data_name(DATA))
        for path in ("makefiles/bindist.build.yaml", "makefiles/vars.flash.yaml", ".dist.yaml",
                     "flash.yaml"):
            with self.subTest(path=path):
                self.assertFalse(D.is_data_name(path))
        for path in ("Makefile.include", ADAPTER, "x.mk", ".inc.mk"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    D.data_name(path)
        with self.assertRaises(ValueError):
            D.adapter_name("makefiles/bindist.build.yaml")

    def test_not_build_or_flash_data(self):
        self.assertEqual(buildeval.build_yaml_name(OWNER),
                         os.path.join(sample.RIOTBASE, "makefiles", "bindist.build.yaml"))
        self.assertFalse(buildeval.is_flash_adapter(ADAPTER))
        self.assertFalse(DATA.endswith(".flash.yaml"))


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
            data = os.path.join(tmp, "bindist.dist.yaml")
            adapter = os.path.join(tmp, "bindist.dist.inc.mk")
            shutil.copy(DATA, data)
            self.assertEqual(self.check([data]).returncode, 1)              # missing
            shutil.copy(ADAPTER, adapter)
            self.assertEqual(self.check([data]).returncode, 0)
            with open(adapter, "a", encoding="utf-8") as file:              # hand-edited
                file.write("DIST_FILES += extra\n")
            res = self.check([data])
            self.assertEqual(res.returncode, 1)
            self.assertIn("is not up to date", res.stderr)
            shutil.copy(ADAPTER, adapter)
            with open(data, "a", encoding="utf-8") as file:                 # stale
                file.write("  - add: {DIST_FILES: [README.md]}\n")
            self.assertEqual(self.check([data]).returncode, 1)
            with open(data, "w", encoding="utf-8") as file:                 # invalid
                file.write("schema: 3\nrules: [{section: x}]\n")
            res = self.check([data])
            self.assertEqual(res.returncode, 1)
            self.assertIn("build data only", res.stderr)
            # generate writes the adapter of valid data
            shutil.copy(DATA, data)
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
        for text in ("DIST_FILES += x", "DIST_FILES=x", "  DIST_FILES := x",
                     "override DIST_FILES += y", "export DIST_FILES ?= z"):
            with self.subTest(text=text):
                self.assertIn("DIST_FILES", assigned(text))
        for text in ("\t@for i in $(DIST_FILES) ; do \\", "# DIST_FILES += x",
                     "X = $(DIST_FILES)", "ifneq (,$(DIST_FILES))"):
            with self.subTest(text=text):
                self.assertNotIn("DIST_FILES", assigned(text))


class ScopeTest(unittest.TestCase):
    """D6."""

    def test_only_adapter_and_application_data_assign_dist_files(self):
        found = []
        for directory, dirs, files in os.walk(sample.RIOTBASE):
            # skip build output and distributions made by `bindist`
            dirs[:] = [d for d in dirs if d not in ("build", "bin") and not d.startswith(".")
                       and not os.path.isfile(os.path.join(directory, d, "Makefile.distcheck"))]
            for name in files:
                if not (name.startswith("Makefile") or name.endswith(".mk")):
                    continue
                path = os.path.join(directory, name)
                try:
                    with open(path, encoding="utf-8") as file:
                        text = file.read()
                except (UnicodeDecodeError, OSError):
                    continue
                if "DIST_FILES" in text and "DIST_FILES" in assigned(text):
                    found.append(os.path.relpath(path, sample.RIOTBASE))
        self.assertEqual(sorted(found), [sample.APP_DIR + "/Makefile",
                                         "makefiles/bindist.dist.inc.mk"])
        with open(os.path.join(sample.RIOTBASE, sample.APP_DIR, "Makefile"),
                  encoding="utf-8") as file:
            self.assertIn("Generated from riot-app.yaml", file.read())


if __name__ == "__main__":
    unittest.main()
