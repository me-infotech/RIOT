#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D6: the flash data is the single source of the programmer settings.

D1 validator: every flash data file of the repository is valid; positive and
   negative samples of the two flash constructs and of Make syntax
D2 generator: exact Make text of `export`, `command` (and negated), other
   rules through config_data's generator
D3 names: Make file <-> flash data <-> adapter
D4 adapters up to date (`generate --check`); a stale or hand-edited adapter
   is found on a copy
D5 each owner Make file includes its adapter as first statement and no
   longer assigns a variable of its flash data (detector with positive and
   negative samples)
D6 scope: the Make files GNU Make reads for `flash` (every programmer of the
   board) assign no flash variable outside the adapters, except the
   documented lines of the flash algorithm (live Make, skipped without it)
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import flash  # noqa: E402
import flashdata as F  # noqa: E402
import rules as R  # noqa: E402
import sample  # noqa: E402

MAKE = shutil.which("make")
ASSIGN = re.compile(r"^\s*(?:export\s+|override\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*(?::{1,3}|\+|\?|!)?=")
# lines of hand-written Make files that set flash variables on purpose: they
# belong to requests outside the data (flash.py check_scope) or to other
# targets than `flash`
ALLOWED = {
    ("Makefile.include", "PROGRAMMER"): "IOTLAB_NODE (out of scope, exit 3)",
    ("Makefile.include", "FLASHFILE"): "IOTLAB_NODE (out of scope, exit 3)",
    ("makefiles/boot/riotboot.mk", "FLASHFILE"): "feature riotboot (out of scope, exit 3)",
}
NO_FLASH_DATA_INCLUDES = {"include $(RIOTMAKE)/tools/dbg_common.inc.mk"}
ALGORITHM_VARS = {"FLASHER", "FFLAGS", "FLASHFILE", "FLASHDEPS", "PROGRAMMER",
                  "PROGRAMMERS_SUPPORTED", "PROGRAMMER_FLASH", "USE_PROGRAMMER_WRAPPER_SCRIPT"}


def assigned(text: str) -> list:
    """Names assigned in a Make text (recipes and comments skipped)."""
    out = []
    for line in text.split("\n"):
        if line.startswith("\t") or line.lstrip().startswith("#"):
            continue
        match = ASSIGN.match(line)
        if match:
            out.append(match.group(1))
    return out


def data_vars(rules: list) -> set:
    names = set()
    for rule in R.walk(rules):
        if "set" in rule:
            names.add(rule["set"]["var"])
        if "add" in rule:
            names |= set(rule["add"])
    return names


class ValidatorTest(unittest.TestCase):
    """D1."""

    def test_repository_data_is_valid(self):
        files = F.all_data()
        self.assertEqual(len(files), 10)
        for path in files:
            with self.subTest(path=os.path.relpath(path, sample.RIOTBASE)):
                F.load(path)

    def test_positive_samples(self):
        for rules in ([{"export": {"targets": "flash ${T}", "vars": ["A", "B"]}}],
                      [{"if": {"command": {"var": "JLINK"}}, "then": [{"add": {"X": ["y"]}}]}],
                      [{"if": {"not": {"command": {"var": "J"}}}, "then": [],
                        "elif": [{"if": {"command": {"var": "K"}}, "then": []}],
                        "else": [{"export": {"targets": "flash%", "vars": ["C"]}}]}],
                      [{"comment": "c", "export": {"targets": "x", "vars": ["V"]}}],
                      [{"set": {"var": "A", "value": "-c 'x [y]'", "flavor": "conditional"}}]):
            with self.subTest(rules=rules):
                self.assertEqual(F.validate({"schema": 3, "rules": rules}), [])

    def test_negative_samples(self):
        for document in (
                {"schema": 1, "rules": []},
                {"schema": 3},
                {"schema": 3, "rules": [], "x": 1},
                {"schema": 3, "rules": [{"export": {"targets": "flash"}}]},
                {"schema": 3, "rules": [{"export": {"targets": "", "vars": ["A"]}}]},
                {"schema": 3, "rules": [{"export": {"targets": "$(T)", "vars": ["A"]}}]},
                {"schema": 3, "rules": [{"export": {"targets": "f", "vars": ["A-B"]}}]},
                {"schema": 3, "rules": [{"export": {"targets": "f", "vars": []}}]},
                {"schema": 3, "rules": [{"export": {"targets": "f", "vars": ["A"]}, "add": {}}]},
                {"schema": 3, "rules": [{"if": {"command": {"var": "$(J)"}}, "then": []}]},
                {"schema": 3, "rules": [{"if": {"command": {}}, "then": []}]},
                {"schema": 3, "rules": [{"if": {"not": {"not": {"command": {"var": "J"}}}},
                                         "then": []}]},
                {"schema": 3, "rules": [{"if": {"command": {"var": "J"}}}]},
                {"schema": 3, "rules": [{"set": {"var": "A", "value": "$(shell x)"}}]},
                {"schema": 3, "rules": [{"if": {"command": {"var": "J"}}, "then": [
                    {"set": {"var": "A", "value": "$(B)"}}]}]}):
            with self.subTest(document=document):
                self.assertNotEqual(F.validate(document), [])


class GeneratorTest(unittest.TestCase):
    """D2."""

    def test_flash_constructs(self):
        rules = [{"export": {"targets": "${JLINK_TARGETS}", "vars": ["A", "B"]}},
                 {"if": {"command": {"var": "JLINK"}},
                  "then": [{"set": {"var": "PROGRAMMER", "value": "jlink",
                                    "flavor": "conditional"}}],
                  "else": [{"set": {"var": "PROGRAMMER", "value": "openocd",
                                    "flavor": "conditional"}}]},
                 {"if": {"not": {"command": {"var": "X"}}},
                  "then": [{"export": {"targets": "flash", "vars": ["C"]}}]}]
        self.assertEqual(F.lines(rules), [
            "$(call target-export-variables,$(JLINK_TARGETS),A B)",
            "",
            "ifneq (,$(shell command -v $(JLINK)))",
            "  PROGRAMMER ?= jlink",
            "else",
            "  PROGRAMMER ?= openocd",
            "endif",
            "",
            "ifeq (,$(shell command -v $(X)))",
            "  $(call target-export-variables,flash,C)",
            "endif"])

    def test_other_rules_and_header(self):
        text = F.make_text([{"comment": "x", "add": {"P": ["a", "b"]}},
                            {"set": {"var": "D", "value": {"select": {
                                "var": "CPU_MODEL", "replace": {"from": "xx", "to": "_xx"}}}}},
                            {"set": {"var": "E", "value": "", "flavor": "conditional"}}],
                           "flash.yaml")
        self.assertEqual(text.split("\n"), [
            "# Generated from flash.yaml by dist/tools/flash/flash.py.",
            "# Do not edit: change flash.yaml and run `just generate-flash-data`.",
            "", "# x", "P += a", "P += b", "D = $(subst xx,_xx,$(CPU_MODEL))", "E ?=", ""])


class NamesTest(unittest.TestCase):
    """D3."""

    def test_names(self):
        self.assertEqual(F.data_name("b/x/Makefile.include"), "b/x/flash.yaml")
        self.assertEqual(F.data_name("m/tools/jlink.inc.mk"), "m/tools/jlink.flash.yaml")
        self.assertEqual(F.adapter_name("b/x/flash.yaml"), "b/x/flash.inc.mk")
        self.assertEqual(F.adapter_name("m/jlink.flash.yaml"), "m/jlink.flash.inc.mk")
        self.assertEqual(F.owner_name("m/jlink.flash.yaml"), "m/jlink.inc.mk")
        self.assertEqual(F.owner_name("b/x/flash.yaml"), "b/x/Makefile.include")
        for bad in ("b/Makefile", "b/Makefile.dep", "m/x.flash.inc.mk", "m/flash.inc.mk",
                    "m/x.mk"):
            with self.subTest(path=bad):
                self.assertRaises(ValueError, F.data_name, bad)
        self.assertRaises(ValueError, F.adapter_name, "b/build.yaml")
        self.assertTrue(F.is_data_name("x/flash.yaml"))
        self.assertFalse(F.is_data_name("x/build.yaml"))

    def test_flash_data_is_no_config_or_build_data(self):
        for path in F.all_data():
            with self.subTest(path=path):
                self.assertFalse(R.is_yaml_name(path))


class AdaptersTest(unittest.TestCase):
    """D4."""

    def test_up_to_date(self):
        self.assertEqual(flash.cmd_generate(check=True), 0)

    def test_stale_and_edited_adapters_are_found(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            data = os.path.join(tmp, "x.flash.yaml")
            with open(data, "w", encoding="utf-8") as file:
                file.write("schema: 3\nrules:\n  - set: {var: A, value: b}\n")
            self.assertEqual(flash.cmd_generate(check=True, files=[data]), 1)   # missing
            self.assertEqual(flash.cmd_generate(check=False, files=[data]), 0)
            self.assertEqual(flash.cmd_generate(check=True, files=[data]), 0)
            with open(F.adapter_name(data), "a", encoding="utf-8") as file:
                file.write("A = c\n")                                        # hand-edited
            self.assertEqual(flash.cmd_generate(check=True, files=[data]), 1)
            flash.cmd_generate(check=False, files=[data])
            with open(data, "a", encoding="utf-8") as file:
                file.write("  - set: {var: B, value: c}\n")                  # stale
            self.assertEqual(flash.cmd_generate(check=True, files=[data]), 1)
            with open(data, "w", encoding="utf-8") as file:
                file.write("schema: 3\nrules:\n  - set: {var: A, value: $(b)}\n")
            self.assertEqual(flash.cmd_generate(check=True, files=[data]), 1)  # invalid


class OwnerTest(unittest.TestCase):
    """D5."""

    def test_adapter_is_the_first_statement(self):
        for path in F.all_data():
            owner = F.owner_name(path)
            with self.subTest(owner=os.path.relpath(owner, sample.RIOTBASE)):
                with open(owner, encoding="utf-8") as file:
                    statements = [line for line in file.read().split("\n")
                                  if line.strip() and not line.lstrip().startswith("#")]
                # leading includes of Make files without flash data (that keeps
                # the order of MAKEFILE_LIST; D6 shows they set no flash variable)
                while statements[0] != F.include_line(path) and \
                        statements[0] in NO_FLASH_DATA_INCLUDES:
                    statements.pop(0)
                self.assertEqual(statements[0], F.include_line(path))

    def test_owner_assigns_no_variable_of_its_data(self):
        for path in F.all_data():
            owner = F.owner_name(path)
            with self.subTest(owner=os.path.relpath(owner, sample.RIOTBASE)):
                with open(owner, encoding="utf-8") as file:
                    left = set(assigned(file.read()))
                self.assertEqual(left & data_vars(F.load(path)), set())

    def test_detector(self):
        self.assertEqual(assigned("A = 1\nB ?= 2\n  C += 3\nexport D := 4\nE::=5\n"
                                  "override F = 6\nG!=x\n"), list("ABCDEFG"))
        self.assertEqual(assigned("# A = 1\n\tB = 2\nifeq ($(C),=)\n$(call x,D=1)\n"
                                  "include E.mk\n"), [])


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class ScopeTest(unittest.TestCase):
    """D6."""

    def make_list(self, programmer: str) -> list:
        res = subprocess.run(
            ["make", "--no-print-directory", "-C", sample.APPS["hello-world"],
             f"BOARD={sample.BOARD}", f"PROGRAMMER={programmer}",
             "info-debug-variable-MAKEFILE_LIST"], cwd=sample.RIOTBASE,
            env=sample.environment(os.environ.get("PATH", "")), capture_output=True, text=True,
            check=True)
        app = os.path.join(sample.RIOTBASE, sample.APPS["hello-world"])
        return sorted({os.path.relpath(os.path.normpath(os.path.join(app, w)), sample.RIOTBASE)
                       for w in res.stdout.split()})

    def test_no_flash_variable_outside_the_data(self):
        flash_vars = set(ALGORITHM_VARS)
        for path in F.all_data():
            rules = F.load(path)
            flash_vars |= data_vars(rules)
            flash_vars |= {v for r in R.walk(rules) if "export" in r for v in r["export"]["vars"]}
        adapters = {os.path.relpath(F.adapter_name(p), sample.RIOTBASE) for p in F.all_data()}
        for programmer in sample.SUPPORTED:
            files = self.make_list(programmer)
            with self.subTest(programmer=programmer):
                self.assertTrue(adapters & set(files))
                for name in files:
                    if name in adapters or name.startswith(sample.APPS["hello-world"]):
                        continue
                    with open(os.path.join(sample.RIOTBASE, name), encoding="utf-8") as file:
                        found = set(assigned(file.read())) & flash_vars
                    found = {v for v in found if (name, v) not in ALLOWED}
                    self.assertEqual(found, set(), name)


if __name__ == "__main__":
    unittest.main()
