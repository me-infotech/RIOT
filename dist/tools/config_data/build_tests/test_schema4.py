#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""B1-B3: schema 4 of the data format (step G0-3) - validator, generator
(Make text of each construct, sections, stand-ins, Doxygen lines) and
evaluator (the build without Make reads the same meaning).

Run: python3 -m unittest discover -s dist/tools/config_data/build_tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# pylint: disable=wrong-import-position
import common as C  # noqa: E402,F401  (sets sys.path)
import generate  # noqa: E402
import rules as R  # noqa: E402
import schema  # noqa: E402
from evaluate import Evaluator, ResolveError  # noqa: E402
from variables import Variables  # noqa: E402


def doc(*rules, version=4):
    return {"schema": version, "rules": list(rules)}


def setv(value, **extra):
    return {"set": {"var": "X", "value": value, **extra}}


class ValidatorTest(unittest.TestCase):
    """B1: the schema 4 constructs are accepted, malformed ones rejected,
    and they need schema 4."""

    VALID = [
        [{"section": "flags"}, {"add": {"CFLAGS": ["-Os"]}}, {"section": "link"}],
        [{"comment": "head"}, {"section": "a"}, {"set": {"var": "A", "value": "1"}}],
        [{"set": {"var": "A", "value": "1"}, "stand_in": "pkg/pkg.mk"}],
        [{"if": {"has": {"var": "U", "match": ["x"]}}, "then": [{"error": "no"}],
          "stand_in": "makefiles/kconfig.mk"}],
        [{"export": ["GENSRC", "Q"]}],
        [{"unexport": ["RCFLAGS"]}],
        [setv("8", export=True)],
        [setv({"when": {"test": {"var": "T"}, "then": "${T}-"}})],
        [setv({"when": {"test": {"var": "Q", "match": ["1"]}, "else": "--verbose"}})],
        [setv({"files": {"match": ["${D}/*.patch"], "sort": True}})],
        [setv({"arith": {"expr": "${RAM_LEN}", "format": "hex", "once": True}})],
        [setv({"arith": {"expr": "${ROM_LEN}-${AUX}", "kilo": ["ROM_LEN"]}})],
        [{"if": {"defined": "LOG_LEVEL"}, "then": []}],
        [{"if": {"not": {"defined": "LOG_LEVEL"}}, "then": []}],
        [{"if": {"count": {"var": "U", "except": ["x"], "is": 1}}, "then": []}],
    ]
    INVALID = [
        ([{"set": {"var": "A", "value": "1"}}, {"section": "a"}], "before the first section"),
        ([{"section": "a"}, {"section": "a"}], "is used twice"),
        ([{"section": "Flags"}], "is not a section name"),
        ([{"section": "a", "set": {"var": "A", "value": "1"}}], "only `section` and `comment`"),
        ([{"if": {"equals": {"A": "1"}}, "then": [{"section": "b"}]}], "only at the top level"),
        ([{"set": {"var": "A", "value": "1"}, "stand_in": "$(RIOTMAKE)/x.mk"}],
         "must be the path of a Make file"),
        ([{"export": []}], "non-empty list of variable names"),
        ([{"unexport": ["$(X)"]}], "is not a variable name"),
        ([setv("1", export="yes")], "export: must be true"),
        ([setv({"when": {"then": "x"}})], "missing key 'test'"),
        ([setv({"when": {"test": {"var": "T"}, "then": "a,b"}})], "`,` is not allowed"),
        ([setv({"when": {"test": {"var": "T"}, "then": "$(T)"}})], "`$` is only allowed"),
        ([setv({"files": {"match": ["*.c"], "sort": 1}})], "must be true or false"),
        ([setv({"arith": {"expr": "1", "once": "yes"}})], "must be true or false"),
        ([setv({"arith": {"expr": "${A}", "kilo": ["B"]}})], "is not used in expr"),
        ([setv({"arith": {"expr": "${A}", "kilo": []}})], "must be a non-empty list"),
        ([{"if": {"defined": "$(X)"}, "then": []}], "is not a variable name"),
        ([{"if": {"count": {"var": "U", "is": -1}}, "then": []}], "number of words"),
        ([{"if": {"count": {"var": "U"}}, "then": []}], "missing key 'is'"),
    ]

    def test_valid(self):
        for rules in self.VALID:
            with self.subTest(rules=rules):
                self.assertEqual(schema.validate(doc(*rules)), [])
                self.assertEqual(R.needed_schema(rules), 4)
                self.assertIn("schema: the rules need schema 4",
                              schema.validate(doc(*rules, version=3)))

    def test_invalid(self):
        for rules, text in self.INVALID:
            with self.subTest(text=text):
                problems = schema.validate(doc(*rules))
                self.assertTrue(any(text in p for p in problems), problems)


class GeneratorTest(unittest.TestCase):
    """B2: the exact Make text of each construct."""

    def test_values(self):
        cases = [
            ({"when": {"test": {"var": "TARGET_ARCH"}, "then": "${TARGET_ARCH}-"}}, None,
             "$(if $(TARGET_ARCH),$(TARGET_ARCH)-)"),
            ({"when": {"test": {"var": "QUIET", "match": ["1"]}, "else": "--verbose"}}, None,
             "$(if $(filter 1,$(QUIET)),,--verbose)"),
            ({"files": {"match": ["${D}/*.patch"], "sort": True}}, None,
             "$(sort $(wildcard $(D)/*.patch))"),
            ({"arith": {"expr": "${RAM_LEN}", "format": "hex", "once": True}}, "CPU_RAM_SIZE",
             '$(call memoized,CPU_RAM_SIZE,$(shell printf "0x%x" $$(($(RAM_LEN:%K=%*1024)))))'),
            ({"arith": {"expr": "${ROM_LEN}-${AUX}", "kilo": ["ROM_LEN"]}}, None,
             "$(shell echo $$(($(ROM_LEN:%K=%*1024)-$(AUX))))"),
            ({"arith": {"expr": "${ROM_LEN}-16K"}}, None,
             "$(shell echo $$(($(ROM_LEN:%K=%*1024)-16*1024)))"),
            ({"select": {"var": "I", "unique": True, "pattern": {"from": "%", "to": "-I%"}}},
             None, "$(patsubst %,-I%,$(strip $(call uniq,$(I))))"),
        ]
        for value, var, text in cases:
            with self.subTest(text=text):
                self.assertEqual(generate.value_text(value, var), text)

    def test_once_needs_a_variable(self):
        with self.assertRaises(generate.NotForMake):
            generate.value_text({"arith": {"expr": "1", "once": True}})

    def test_conditions(self):
        self.assertEqual(generate.condition({"defined": "X"}), "ifdef X")
        self.assertEqual(generate.condition({"not": {"defined": "X"}}), "ifndef X")
        self.assertEqual(generate.condition({"count": {"var": "U", "is": 1}}),
                         "ifeq (1,$(words $(U)))")
        self.assertEqual(generate.condition(
            {"not": {"count": {"var": "U", "except": ["a"], "is": 0}}}),
            "ifneq (0,$(words $(filter-out a,$(U))))")

    def test_actions(self):
        text = generate.lines([setv("8", export=True), {"export": ["A", "B"]},
                               {"unexport": ["C"]}])
        self.assertEqual(text, ["export X = 8", "export A", "export B", "unexport C"])

    def test_doxygen_lines(self):
        self.assertEqual(generate.lines([{"comment": "# @defgroup g\n#\nplain\n",
                                          "add": {"P": ["a"]}}]),
                         ["## @defgroup g", "##", "# plain", "#", "P += a"])

    def test_stand_in_rules_are_left_out(self):
        rules = [{"set": {"var": "A", "value": "1"}, "stand_in": "x.mk"},
                 {"if": {"defined": "K"}, "then": [{"error": "k"}], "stand_in": "x.mk"},
                 {"if": {"equals": {"Q": "1"}}, "then": [
                     {"add": {"B": ["1"]}, "stand_in": "x.mk"}, {"add": {"C": ["1"]}}]}]
        self.assertEqual(generate.lines(generate.for_make(rules)),
                         ["ifeq ($(Q),1)", "  C += 1", "endif"])

    def test_sections(self):
        text = generate.make_text([{"section": "a"}, {"set": {"var": "X", "value": "1"}},
                                   {"section": "b", "comment": "second"},
                                   {"add": {"Y": ["2"]}}], "build.yaml", "Makefile.include")
        self.assertEqual(text.split("\n")[2:], [
            "# The build part of Makefile.include, which includes this file once per",
            "# section with RIOT_BUILD_SECTION set to the name of the section.", "",
            "ifeq (a,$(RIOT_BUILD_SECTION))", "  RIOT_BUILD_SECTION :=", "  X = 1", "endif", "",
            "# second", "ifeq (b,$(RIOT_BUILD_SECTION))", "  RIOT_BUILD_SECTION :=",
            "  Y += 2", "endif", "",
            "ifneq (,$(RIOT_BUILD_SECTION))",
            "  $(error Makefile.include: no build section $(RIOT_BUILD_SECTION))", "endif", ""])

    def test_part_without_sections(self):
        text = generate.make_text([{"add": {"Y": ["2"]}}], "build.yaml", "cpu/x/Makefile.include")
        self.assertEqual(text.split("\n")[2:5], [
            "# The build part of cpu/x/Makefile.include, which includes this file.", "",
            "Y += 2"])


class EvaluatorTest(unittest.TestCase):
    """B3: the build without Make reads the schema 4 constructs with the
    meaning of the generated Make."""

    def run_rules(self, rules, **values):
        v = Variables()
        v.set("CURDIR", os.path.dirname(os.path.abspath(__file__)), "simple")
        for name, value in values.items():
            v.set(name, value)
        ev = Evaluator(v, v.get("CURDIR"))
        ev.run(rules)
        return v

    def test_when_is_lazy(self):
        v = self.run_rules([setv({"when": {"test": {"var": "T"}, "then": "${T}-"}})])
        self.assertEqual(v.get("X"), "")
        v.set("T", "arm-none-eabi")
        self.assertEqual(v.get("X"), "arm-none-eabi-")
        v = self.run_rules([setv({"when": {"test": {"var": "Q", "match": ["1"]},
                                           "else": "--verbose"}})], Q="0")
        self.assertEqual(v.get("X"), "--verbose")

    def test_defined_is_ifdef(self):
        rule = [{"if": {"defined": "L"}, "then": [{"add": {"R": ["yes"]}}]}]
        self.assertEqual(self.run_rules(rule, L="4").get("R"), "yes")
        self.assertEqual(self.run_rules(rule).get("R"), "")
        self.assertEqual(self.run_rules(rule, L="").get("R"), "")
        # ifdef does not expand: a reference to an empty variable counts
        self.assertEqual(self.run_rules(rule, L="${EMPTY}").get("R"), "yes")

    def test_count_is_words(self):
        rule = [{"if": {"count": {"var": "U", "except": ["s"], "is": 1}},
                 "then": [{"add": {"R": ["one"]}}]}]
        self.assertEqual(self.run_rules(rule, U="a s").get("R"), "one")
        self.assertEqual(self.run_rules(rule, U="a b").get("R"), "")
        self.assertEqual(self.run_rules(rule, U="a a").get("R"), "")   # repetitions count

    def test_export_and_unexport(self):
        v = self.run_rules([{"export": ["A", "B"]}, setv("1", export=True), {"export": ["A"]},
                            {"unexport": ["B"]}])
        self.assertEqual(v.words("BUILD_EXPORTED"), ["A", "X"])

    def test_sorted_files(self):
        here = os.path.basename(__file__)
        v = self.run_rules([setv({"files": {"match": ["test_*.py", "common.py"],
                                            "sort": True}})])
        self.assertEqual(v.words("X"), sorted(v.words("X")))
        self.assertIn(here, v.words("X"))

    def test_kilo_only_in_the_named_variables(self):
        spec = {"arith": {"expr": "${R}-${A}", "kilo": ["R"]}}
        self.assertEqual(self.run_rules([setv(spec)], R="4K", A="1024").get("X"), "3072")
        with self.assertRaises(ValueError):
            self.run_rules([setv(spec)], R="4K", A="1K").get("X")

    def test_unique_before_the_pattern(self):
        v = self.run_rules([setv({"select": {"var": "I", "unique": True,
                                             "pattern": {"from": "%", "to": "-I%"}}})],
                           I="a b a c")
        self.assertEqual(v.get("X"), "-Ia -Ib -Ic")

    def test_stand_in_and_section_rules_are_read(self):
        with self.assertRaises(ResolveError):
            self.run_rules([{"section": "a"},
                            {"if": {"nonempty": ["K"]}, "then": [{"error": "outside"}],
                             "stand_in": "x.mk"}], K="y")


if __name__ == "__main__":
    unittest.main()
