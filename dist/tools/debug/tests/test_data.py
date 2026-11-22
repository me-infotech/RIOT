#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D5: the data of step G2B-2 (the setsid rule of macOS, decision D4).

D1 validator: the condition `goal: TARGET` and the word `${NAME}` in the
   vars of `export` (P1); positive and negative samples
D2 generator: the exact Make text of both constructs (negated goal too)
D3 single source: Makefile.include keeps no line of the rule; debug.yaml
   holds it, the generated debug.inc.mk has Make's statements of the base
   (the export of $(SETSID) included, Make's bug kept) and is up to date
D4 evaluation of the rule without Make: DEBUGDEPS and the export only for
   OS=Darwin, the goal `debug` and no setsid on PATH
D5 the debugger data the step reads exist for the three programmers
   (openocd, jlink, bmp) and none for pyocd
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import debug_sample as S  # noqa: E402
import term as TM  # noqa: E402
import termdata as T  # noqa: E402
import flash as FL  # noqa: E402

ROOT = S.RIOTBASE
# the statements of Makefile.include:577-586 at the base, as generated now
RULE = [
    "ifeq ($(OS),Darwin)",
    "  ifneq (,$(filter debug,$(MAKECMDGOALS)))",
    "    ifeq (,$(shell command -v setsid 2>/dev/null))",
    "      SETSID = $(RIOTTOOLS)/setsid/setsid",
    "      $(call target-export-variables,debug,$(SETSID))",
    "      DEBUGDEPS += $(SETSID)",
    "    endif",
    "  endif",
    "endif",
]


def doc(rules):
    return {"schema": 4, "rules": rules}


class ValidatorTest(unittest.TestCase):
    """D1."""

    def test_positive(self):
        for rules in ([{"if": {"goal": "debug"}, "then": [{"set": {"var": "A", "value": "1"}}]}],
                      [{"if": {"not": {"goal": "debug-server"}},
                        "then": [{"set": {"var": "A", "value": "1"}}]}],
                      [{"export": {"targets": "debug", "vars": ["${SETSID}"]}}],
                      [{"export": {"targets": "debug", "vars": ["A", "${B}"]}}]):
            with self.subTest(rules=rules):
                self.assertEqual(T.validate(doc(rules)), [])

    def test_negative(self):
        then = [{"set": {"var": "A", "value": "1"}}]
        for rules in ([{"if": {"goal": "debug x"}, "then": then}],
                      [{"if": {"goal": ""}, "then": then}],
                      [{"if": {"goal": ["debug"]}, "then": then}],
                      [{"export": {"targets": "debug", "vars": ["$(SETSID)"]}}],
                      [{"export": {"targets": "debug", "vars": ["${A B}"]}}],
                      [{"export": {"targets": "debug", "vars": ["A-B"]}}],
                      [{"export": {"targets": "debug", "vars": []}}],
                      [{"export": {"targets": "", "vars": ["A"]}}],
                      [{"export": {"targets": "debug", "vars": ["A"]}, "x": 1}]):
            with self.subTest(rules=rules):
                self.assertNotEqual(T.validate(doc(rules)), [])


class GeneratorTest(unittest.TestCase):
    """D2."""

    def test_constructs(self):
        then = [{"set": {"var": "A", "value": "1"}}]
        self.assertEqual(T.lines([{"if": {"goal": "debug"}, "then": then}]),
                         ["ifneq (,$(filter debug,$(MAKECMDGOALS)))", "  A = 1", "endif"])
        self.assertEqual(T.lines([{"if": {"not": {"goal": "debug"}}, "then": then}])[0],
                         "ifeq (,$(filter debug,$(MAKECMDGOALS)))")
        self.assertEqual(T.lines([{"export": {"targets": "debug", "vars": ["A", "${B}"]}}]),
                         ["$(call target-export-variables,debug,A $(B))"])


class SingleSourceTest(unittest.TestCase):
    """D3."""

    def test_rule_is_data(self):
        with open(os.path.join(ROOT, "Makefile.include"), encoding="utf-8") as file:
            text = file.read()
        self.assertNotIn("SETSID", text)
        self.assertNotIn("command -v setsid", text)
        self.assertEqual(text.count("include $(RIOTBASE)/debug.inc.mk\n"), 1)
        with open(os.path.join(ROOT, "debug.inc.mk"), encoding="utf-8") as file:
            adapter = file.read().split("\n")
        start = adapter.index(RULE[0])
        self.assertEqual(adapter[start:start + len(RULE)], RULE)
        self.assertEqual(TM.cmd_generate(True, [os.path.join(ROOT, "debug.yaml")]), 0)


def evaluate(goal, os_name="Darwin", setsid=False):
    real = FL.command_found
    with mock.patch.object(FL, "command_found",
                           side_effect=lambda name: setsid if name == "setsid" else real(name)):
        ev = TM.evaluate(os.path.join(ROOT, S.APPS["hello-world"]),
                         {"BOARD": S.BOARD, "PROGRAMMER": "openocd", "OS": os_name}, {},
                         goals=(goal,), termdeps=False)
    return ev


class EvaluationTest(unittest.TestCase):
    """D4."""

    def test_darwin_debug_without_setsid(self):
        ev = evaluate("debug")
        path = os.path.join(ROOT, "dist", "tools", "setsid", "setsid")
        self.assertEqual(ev.v.get("SETSID").strip(), path)
        self.assertEqual(ev.v.words("DEBUGDEPS"), [path])
        self.assertIn((["debug"], [path]), ev.exports)

    def test_other_cases_have_no_rule(self):
        for goal, os_name, setsid in (("debug-server", "Darwin", False),
                                      ("debug-client", "Darwin", False),
                                      ("debug", "Darwin", True), ("debug", "Linux", False)):
            with self.subTest(goal=goal, os=os_name, setsid=setsid):
                ev = evaluate(goal, os_name, setsid)
                self.assertEqual(ev.v.words("DEBUGDEPS"), [])
                self.assertFalse(ev.v.defined("SETSID"))


class ProgrammerDataTest(unittest.TestCase):
    """D5."""

    def test_debugger_data(self):
        tools = os.path.join(ROOT, "makefiles", "tools")
        for programmer in S.PROGRAMMERS:
            with self.subTest(programmer=programmer):
                rules = T.load(T.data_name(os.path.join(tools, f"{programmer}.inc.mk"), "debug"))
                names = {r["set"]["var"] for r in rules if "set" in r}
                self.assertIn("DEBUGGER", names)
        self.assertFalse(os.path.exists(os.path.join(tools, "pyocd.debug.yaml")))


if __name__ == "__main__":
    unittest.main()
