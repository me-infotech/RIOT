#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D6: the terminal and debugger data is the single source.

D1 validator: every data file of the step is valid; positive and negative
   samples of the three constructs (`command: {name}`, `word`, `set` with
   `export`) and of Make syntax
D2 generator: exact Make text of the constructs (and of the flash and
   configuration rules through their generators); `stand_in` rules are left
   out
D3 names: Make file <-> data <-> adapter for both kinds
D4 adapters up to date (`generate --check`); a missing, stale or
   hand-edited adapter is found on a copy
D5 each owner includes its adapter (after its flash adapter and the
   documented leading includes) and no longer assigns a variable of its
   data; `stand_in` names the owner (detector with positive and negative
   samples)
D6 scope: the Make files GNU Make reads for `term` (every terminal and
   programmer of the board) assign no terminal or debugger variable outside
   the adapters (live Make, skipped without it)
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
import term  # noqa: E402
import termdata as T  # noqa: E402
import flashdata as F  # noqa: E402
import rules as R  # noqa: E402
import sample  # noqa: E402

MAKE = shutil.which("make")
ASSIGN = re.compile(r"^\s*(?:export\s+|override\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*(?::{1,3}|\+|\?|!)?=")
# the data files of the step
DATA = sorted([
    "debug.yaml", "boards/common/nrf52/term.yaml", "boards/nrf52840dk/term.yaml",
    "makefiles/tools/serial.term.yaml", "makefiles/tools/dbg_common.debug.yaml",
    "makefiles/tools/gdb.debug.yaml", "makefiles/tools/jlink.debug.yaml",
    "makefiles/tools/openocd.debug.yaml", "makefiles/tools/bmp.debug.yaml",
    "makefiles/toolchain/gnu.debug.yaml"])
# statements an owner keeps before its adapter: the flash adapter (G3-2), the
# include of dbg_common.inc.mk (no flash data; a stand_in of the debugger
# data), the build part of gnu.inc.mk (Make reads gdb.inc.mk after it, as
# before)
LEADING = {"include $(RIOTMAKE)/tools/dbg_common.inc.mk",
           "include $(RIOTMAKE)/toolchain/gnu.build.mk"}
# Makefile.include includes debug.inc.mk where DEBUG_ELFFILE was (:454,
# after riotboot.mk, which may set it first)
NOT_FIRST = {"debug.yaml"}
# lines of hand-written Make files that set terminal or debugger variables on
# purpose: requests outside the data (term.py check_scope: exit 3)
ALLOWED = {
    ("makefiles/boot/riotboot.mk", "DEBUG_ELFFILE"): "riotboot (exit 3)",
    ("Makefile.include", "TERMDEPS"): "`TERMDEPS += $(TERMFLASHDEPS)` (rule of term, "
                                      "algorithm) and EMULATE=1 (exit 3)",
    ("Makefile.include", "DEBUGDEPS"): "EMULATE=1 (exit 3), setsid on macOS (debug)",
}


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


def doc(rules):
    return {"schema": 4, "rules": rules}


class ValidatorTest(unittest.TestCase):
    """D1."""

    def test_repository_data_is_valid(self):
        files = T.all_data()
        self.assertEqual([os.path.relpath(p, sample.RIOTBASE) for p in files], DATA)
        for path in files:
            with self.subTest(path=os.path.relpath(path, sample.RIOTBASE)):
                T.load(path)

    def test_positive_samples(self):
        for rules in (
                [{"if": {"command": {"name": "pyserial-miniterm.py"}}, "then": []}],
                [{"if": {"not": {"command": {"name": "x"}}}, "then": [],
                  "elif": [{"if": {"command": {"var": "J"}}, "then": []}]}],
                [{"set": {"var": "P", "value": {"word": {"var": "T", "index": 1}}}}],
                [{"set": {"var": "P", "value": {"word": {"var": "T", "index": -1}},
                          "flavor": "simple"}}],
                [{"comment": "c", "set": {"var": "P", "value": {"word": {"var": "T", "index": 2}},
                                          "flavor": "conditional", "export": True}}],
                [{"set": {"var": "BAUD", "value": "115200", "flavor": "conditional",
                          "export": True}}],
                [{"export": {"targets": "term cleanterm", "vars": ["A"]}}],
                [{"include": {"path": "${RIOTMAKE}/tools/x.inc.mk"},
                  "stand_in": "makefiles/tools/y.inc.mk"}],
                [{"if": {"equals": {"MOST_RECENT_PORT": "1"}}, "then": [
                    {"set": {"var": "P", "value": {"word": {"var": "T", "index": 1}}}}]}]):
            with self.subTest(rules=rules):
                self.assertEqual(T.validate(doc(rules)), [])

    def test_negative_samples(self):
        for document in (
                {"schema": 3, "rules": []},
                {"schema": 4},
                {"schema": 4, "rules": [], "x": 1},
                doc([{"section": "board"}]),
                doc([{"if": {"command": {"name": "a b"}}, "then": []}]),
                doc([{"if": {"command": {"name": "$(X)"}}, "then": []}]),
                doc([{"if": {"command": {"name": "x", "var": "Y"}}, "then": []}]),
                doc([{"if": {"not": {"not": {"command": {"name": "x"}}}}, "then": []}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T", "index": 0}}}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T", "index": -2}}}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T", "index": "1"}}}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "$(T)", "index": 1}}}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T"}}}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T", "index": 1}},
                              "export": False}}]),
                doc([{"set": {"var": "P", "value": {"word": {"var": "T", "index": 1}}},
                      "add": {}}]),
                doc([{"set": {"var": "A", "value": "$(shell date)"}}]),
                doc([{"if": {"command": {"name": "x"}}, "then": [
                    {"set": {"var": "A", "value": "$(B)"}}]}]),
                doc([{"export": {"targets": "term", "vars": []}}])):
            with self.subTest(document=document):
                self.assertNotEqual(T.validate(document), [])


class GeneratorTest(unittest.TestCase):
    """D2."""

    def test_constructs(self):
        rules = [{"if": {"command": {"name": "pyserial-miniterm.py"}},
                  "then": [{"set": {"var": "TERMPROG", "value": "pyserial-miniterm.py",
                                    "flavor": "conditional"}}],
                  "elif": [{"if": {"not": {"command": {"name": "miniterm"}}}, "then": []}],
                  "else": [{"error": "not found"}]},
                 {"set": {"var": "A", "value": {"word": {"var": "T", "index": 1}},
                          "flavor": "simple"}},
                 {"set": {"var": "B", "value": {"word": {"var": "T", "index": -1}}}},
                 {"set": {"var": "C", "value": {"word": {"var": "U", "index": 2}},
                          "flavor": "conditional"}},
                 {"set": {"var": "BAUD", "value": "115200", "flavor": "conditional",
                          "export": True}},
                 {"export": {"targets": "term cleanterm", "vars": ["X"]}},
                 {"include": {"path": "${RIOTMAKE}/x.inc.mk"}, "stand_in": "makefiles/y.inc.mk"},
                 {"if": {"command": {"var": "JLINK"}}, "then": [{"add": {"P": ["a"]}}]}]
        self.assertEqual(T.make_text(rules, "x.term.yaml").split("\n"), [
            "# Generated from x.term.yaml by dist/tools/term/term.py.",
            "# Do not edit: change x.term.yaml and run `just generate-term-data`.",
            "",
            "ifneq (,$(shell command -v pyserial-miniterm.py 2>/dev/null))",
            "  TERMPROG ?= pyserial-miniterm.py",
            "else ifeq (,$(shell command -v miniterm 2>/dev/null))",
            "else",
            "  $(error not found)",
            "endif",
            "",
            "A := $(firstword $(T))",
            "B = $(lastword $(T))",
            "C ?= $(word 2,$(U))",
            "export BAUD ?= 115200",
            "$(call target-export-variables,term cleanterm,X)",
            "",
            "ifneq (,$(shell command -v $(JLINK)))",
            "  P += a",
            "endif",
            ""])


class NamesTest(unittest.TestCase):
    """D3."""

    def test_names(self):
        self.assertEqual(T.data_name("b/x/Makefile.include", "term"), "b/x/term.yaml")
        self.assertEqual(T.data_name("b/x/Makefile.include", "debug"), "b/x/debug.yaml")
        self.assertEqual(T.data_name("m/tools/serial.inc.mk", "term"), "m/tools/serial.term.yaml")
        self.assertEqual(T.data_name("m/tools/jlink.inc.mk", "debug"), "m/tools/jlink.debug.yaml")
        self.assertEqual(T.adapter_name("b/x/term.yaml"), "b/x/term.inc.mk")
        self.assertEqual(T.adapter_name("m/gdb.debug.yaml"), "m/gdb.debug.inc.mk")
        self.assertEqual(T.owner_name("m/gdb.debug.yaml"), "m/gdb.inc.mk")
        self.assertEqual(T.owner_name("b/x/term.yaml"), "b/x/Makefile.include")
        self.assertEqual(T.include_line(os.path.join(sample.RIOTBASE, "debug.yaml")),
                         "include $(RIOTBASE)/debug.inc.mk")
        self.assertEqual(T.include_line(os.path.join(sample.RIOTBASE, "makefiles", "tools",
                                                     "serial.term.yaml")),
                         "include $(RIOTMAKE)/tools/serial.term.inc.mk")
        for bad in ("b/Makefile", "m/x.term.inc.mk", "m/x.debug.inc.mk", "m/x.flash.inc.mk",
                    "m/term.inc.mk", "m/x.mk"):
            with self.subTest(path=bad):
                self.assertRaises(ValueError, T.data_name, bad, "term")
        self.assertRaises(ValueError, T.adapter_name, "b/flash.yaml")
        self.assertTrue(T.is_data_name("x/term.yaml"))
        self.assertTrue(T.is_data_name("x/a.debug.yaml"))
        self.assertFalse(T.is_data_name("x/build.yaml"))
        self.assertFalse(T.is_data_name("x/flash.yaml"))
        self.assertFalse(T.is_data_name("x/.term.yaml"))

    def test_data_is_no_config_build_or_flash_data(self):
        for path in T.all_data():
            with self.subTest(path=path):
                self.assertFalse(R.is_yaml_name(path))
                self.assertFalse(F.is_data_name(path))


class AdaptersTest(unittest.TestCase):
    """D4."""

    def test_up_to_date(self):
        self.assertEqual(term.cmd_generate(check=True), 0)

    def test_stale_and_edited_adapters_are_found(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            data = os.path.join(tmp, "x.term.yaml")
            with open(data, "w", encoding="utf-8") as file:
                file.write("schema: 4\nrules:\n  - set: {var: A, value: b}\n")
            self.assertEqual(term.cmd_generate(check=True, files=[data]), 1)   # missing
            self.assertEqual(term.cmd_generate(check=False, files=[data]), 0)
            self.assertEqual(term.cmd_generate(check=True, files=[data]), 0)
            with open(T.adapter_name(data), "a", encoding="utf-8") as file:
                file.write("A = c\n")                                        # hand-edited
            self.assertEqual(term.cmd_generate(check=True, files=[data]), 1)
            term.cmd_generate(check=False, files=[data])
            with open(data, "a", encoding="utf-8") as file:
                file.write("  - set: {var: B, value: c}\n")                  # stale
            self.assertEqual(term.cmd_generate(check=True, files=[data]), 1)
            with open(data, "w", encoding="utf-8") as file:
                file.write("schema: 4\nrules:\n  - set: {var: A, value: $(b)}\n")
            self.assertEqual(term.cmd_generate(check=True, files=[data]), 1)  # invalid


def statements(path: str) -> list:
    with open(path, encoding="utf-8") as file:
        return [line for line in file.read().split("\n")
                if line.strip() and not line.lstrip().startswith("#")]


class OwnerTest(unittest.TestCase):
    """D5."""

    def test_owner_includes_its_adapter(self):
        for path in T.all_data():
            owner = T.owner_name(path)
            name = os.path.relpath(path, sample.RIOTBASE)
            with self.subTest(owner=os.path.relpath(owner, sample.RIOTBASE)):
                lines = statements(owner)
                self.assertEqual(lines.count(T.include_line(path)), 1)
                if name in NOT_FIRST:
                    continue
                flash = F.data_name(owner)
                while lines[0] != T.include_line(path) and (
                        lines[0] in LEADING
                        or (os.path.isfile(flash) and lines[0] == F.include_line(flash))):
                    lines.pop(0)
                self.assertEqual(lines[0], T.include_line(path))

    def test_owner_assigns_no_variable_of_its_data(self):
        for path in T.all_data():
            owner = T.owner_name(path)
            with self.subTest(owner=os.path.relpath(owner, sample.RIOTBASE)):
                with open(owner, encoding="utf-8") as file:
                    left = set(assigned(file.read()))
                self.assertEqual(left & data_vars(T.load(path)), set())

    def test_stand_in_names_the_owner_and_is_not_generated(self):
        found = 0
        for path in T.all_data():
            owner = os.path.relpath(T.owner_name(path), sample.RIOTBASE)
            for rule in R.walk(T.load(path)):
                if "stand_in" in rule:
                    found += 1
                    self.assertEqual(rule["stand_in"], owner)
                    with open(T.adapter_name(path), encoding="utf-8") as file:
                        self.assertNotIn("dbg_common.inc.mk", file.read())
                    # the owner does what the rule stands for itself
                    self.assertIn("include $(RIOTMAKE)/tools/dbg_common.inc.mk",
                                  statements(T.owner_name(path)))
        self.assertEqual(found, 2)

    def test_detector(self):
        self.assertEqual(assigned("A = 1\nB ?= 2\n  C += 3\nexport D := 4\nE::=5\n"
                                  "override F = 6\nG!=x\n"), list("ABCDEFG"))
        self.assertEqual(assigned("# A = 1\n\tB = 2\nifeq ($(C),=)\n$(call x,D=1)\n"
                                  "include E.mk\n"), [])


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class ScopeTest(unittest.TestCase):
    """D6."""

    def make_list(self, variables: dict) -> list:
        res = subprocess.run(
            ["make", "--no-print-directory", "-C", sample.APPS["hello-world"],
             f"BOARD={sample.BOARD}", *[f"{k}={v}" for k, v in variables.items()],
             "info-debug-variable-MAKEFILE_LIST"], cwd=sample.RIOTBASE,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/"),
                 "LC_ALL": "C"}, capture_output=True, text=True, check=True)
        app = os.path.join(sample.RIOTBASE, sample.APPS["hello-world"])
        return sorted({os.path.relpath(os.path.normpath(os.path.join(app, w)), sample.RIOTBASE)
                       for w in res.stdout.split()})

    def test_no_terminal_variable_outside_the_data(self):
        names = set()
        for path in T.all_data():
            rules = T.load(path)
            names |= data_vars(rules)
            names |= {v for r in R.walk(rules) if "export" in r and isinstance(r["export"], dict)
                      for v in r["export"]["vars"]}
        adapters = {os.path.relpath(T.adapter_name(p), sample.RIOTBASE) for p in T.all_data()}
        for variables in ({}, {"PROGRAMMER": "jlink", "RIOT_TERMINAL": "jlink"},
                          {"PROGRAMMER": "bmp", "RIOT_TERMINAL": "semihosting"},
                          {"RIOT_TERMINAL": "openocd-rtt"}):
            files = self.make_list(variables)
            with self.subTest(variables=variables):
                self.assertTrue(adapters & set(files))
                for name in files:
                    if name in adapters or name.startswith(sample.APPS["hello-world"]):
                        continue
                    with open(os.path.join(sample.RIOTBASE, name), encoding="utf-8") as file:
                        found = set(assigned(file.read())) & names
                    found = {v for v in found if (name, v) not in ALLOWED}
                    self.assertEqual(found, set(), name)


if __name__ == "__main__":
    unittest.main()
