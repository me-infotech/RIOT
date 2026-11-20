#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C3: the generator writes the Make text of each rule, deterministic and
with the header that names the source.

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from generate import condition, lines, make_text  # noqa: E402

SEL = {"var": "USEMODULE", "match": ["a", "b%"]}


class ConditionTextTest(unittest.TestCase):

    def test_each_condition_and_its_negation(self):
        cases = [
            ({"has": SEL}, "ifneq (,$(filter a b%,$(USEMODULE)))"),
            ({"has": {**SEL, "except": ["b1", "b2"]}},
             "ifneq (,$(filter a b%,$(filter-out b1 b2,$(USEMODULE))))"),
            ({"selection_equals": {**SEL, "words": ["b%"]}},
             "ifeq (b%,$(filter a b%,$(USEMODULE)))"),
            ({"one_of": {"var": "CPU_CORE", "values": ["m4f", "m7"]}},
             "ifneq (,$(filter $(CPU_CORE),m4f m7))"),
            ({"equals": {"OS": "Linux"}}, "ifeq ($(OS),Linux)"),
            ({"equals": {"OS": "Linux", "OS_ARCH": "x86_64"}},
             "ifeq ($(OS) $(OS_ARCH),Linux x86_64)"),
            ({"equals": {"CPU": ""}}, "ifeq ($(CPU),)"),
        ]
        flip = {"ifeq": "ifneq", "ifneq": "ifeq"}
        for cond, text in cases:
            with self.subTest(cond=cond):
                self.assertEqual(condition(cond), text)
                kind, rest = text.split(" ", 1)
                self.assertEqual(condition({"not": cond}), f"{flip[kind]} {rest}")


class RuleTextTest(unittest.TestCase):

    def test_actions(self):
        rules = [
            {"add": {"USEMODULE": ["a", "cpu_${CPU}"]}},
            {"set": {"var": "A", "value": "x"}},
            {"set": {"var": "B", "value": "${A}", "flavor": "simple"}},
            {"set": {"var": "C", "value": "1", "flavor": "conditional"}},
            {"include": {"path": "${RIOTBOARD}/x/Makefile.dep"}},
            {"include": {"path": "${APPDIR}/y.dep", "optional": True}},
            {"include": {"for_each": "PKG_PATHS", "path": "%Makefile.dep", "optional": True}},
            {"include": {"for_each": "USEMODULE", "path": "${RIOTBASE}/sys/%/Makefile.dep",
                         "sort": True, "optional": True}},
            {"error": "${BOARD}: no CPU"}, {"warning": "w"}, {"info": "i"},
        ]
        self.assertEqual(lines(rules), [
            "USEMODULE += a", "USEMODULE += cpu_$(CPU)",
            "A = x", "B := $(A)", "C ?= 1",
            "include $(RIOTBOARD)/x/Makefile.dep",
            "-include $(APPDIR)/y.dep",
            "-include $(PKG_PATHS:%=%Makefile.dep)",
            "-include $(sort $(USEMODULE:%=$(RIOTBASE)/sys/%/Makefile.dep))",
            "$(error $(BOARD): no CPU)", "$(warning w)", "$(info i)"])

    def test_branches_comments_and_layout(self):
        rules = [
            {"comment": "header\n\nmore"},
            {"add": {"V": ["a"]}},
            {"comment": "why", "if": {"equals": {"C": "m0"}},
             "then": [{"set": {"var": "A", "value": "6"}}],
             "elif": [{"comment": "m3", "if": {"equals": {"C": "m3"}},
                       "then": [{"if": {"has": {"var": "U", "match": ["x"]}},
                                 "then": [{"add": {"U": ["y"]}}]}]}],
             "else": [{"error": "unknown"}]},
            {"add": {"V": ["b"]}},
        ]
        self.assertEqual(lines(rules), [
            "# header", "#", "# more",
            "",
            "V += a",
            "",
            "# why",
            "ifeq ($(C),m0)", "  A = 6",
            "# m3",
            "else ifeq ($(C),m3)",
            "  ifneq (,$(filter x,$(U)))", "    U += y", "  endif",
            "else", "  $(error unknown)",
            "endif",
            "",
            "V += b"])

    def test_header_names_the_source_and_the_recipe(self):
        text = make_text([{"add": {"V": ["a"]}}], "deps.yaml")
        self.assertTrue(text.startswith("# Generated from deps.yaml by "
                                        "dist/tools/config_data/config_data.py.\n"
                                        "# Do not edit: change deps.yaml and run "
                                        "`just generate-config-data`.\n\n"))
        self.assertTrue(text.endswith("V += a\n"))

    def test_deterministic(self):
        rules = [{"if": {"has": SEL}, "then": [{"add": {"V": ["a", "b"]}}]}]
        self.assertEqual(make_text(rules, "x.yaml"), make_text(rules, "x.yaml"))


if __name__ == "__main__":
    unittest.main()
