#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C2: the translator turns each supported Make statement into its
structured rule and rejects everything else with file and line.

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from translate import Unsupported, condition, translate  # noqa: E402

USEMODULE_SEL = {"var": "USEMODULE", "match": ["gnrc_%"]}


def cond(line: str) -> dict:
    kind, args = line.split(None, 1)
    return condition(kind, args)


class ConditionTest(unittest.TestCase):
    """Each condition form, in both argument orders and with blanks."""

    def test_has_and_its_negation(self):
        self.assertEqual(cond("ifneq (,$(filter gnrc_%,$(USEMODULE)))"), {"has": USEMODULE_SEL})
        self.assertEqual(cond("ifeq (,$(filter gnrc_%,$(USEMODULE)))"),
                         {"not": {"has": USEMODULE_SEL}})

    def test_blanks_and_argument_order_do_not_matter(self):
        for line in ("ifneq (,$(filter gnrc_%, $(USEMODULE)))",
                     "ifneq ( , $(filter  gnrc_% ,$(USEMODULE) ))",
                     "ifneq ($(filter gnrc_%,$(USEMODULE)),)"):
            with self.subTest(line=line):
                self.assertEqual(cond(line), {"has": USEMODULE_SEL})

    def test_several_patterns(self):
        self.assertEqual(cond("ifneq (,$(filter a b% c,$(FEATURES_USED)))"),
                         {"has": {"var": "FEATURES_USED", "match": ["a", "b%", "c"]}})

    def test_filter_out_inside_and_outside_mean_the_same(self):
        expected = {"has": {"var": "USEMODULE", "match": ["netdev_%"],
                            "except": ["netdev_default", "netdev_legacy_api"]}}
        self.assertEqual(cond("ifneq (,$(filter netdev_%,"
                              "$(filter-out netdev_default netdev_legacy_api,$(USEMODULE))))"),
                         expected)
        self.assertEqual(cond("ifneq (,$(filter-out netdev_default netdev_legacy_api, "
                              "$(filter netdev_%,$(USEMODULE))))"), expected)

    def test_selection_equals(self):
        expected = {"selection_equals": {"var": "USEMODULE", "match": ["periph_rtc", "periph_rtt"],
                                         "words": ["periph_rtt"]}}
        self.assertEqual(cond("ifeq (periph_rtt,$(filter periph_rtc periph_rtt,$(USEMODULE)))"),
                         expected)
        self.assertEqual(cond("ifneq ($(filter periph_rtc periph_rtt,$(USEMODULE)),periph_rtt)"),
                         {"not": expected})

    def test_one_of(self):
        expected = {"one_of": {"var": "CPU_CORE", "values": ["cortex-m4f", "cortex-m7"]}}
        self.assertEqual(cond("ifneq (,$(filter $(CPU_CORE),cortex-m4f cortex-m7))"), expected)
        self.assertEqual(cond("ifeq (,$(filter $(CPU_CORE),cortex-m4f cortex-m7))"),
                         {"not": expected})

    def test_equals(self):
        self.assertEqual(cond("ifeq ($(OS),Linux)"), {"equals": {"OS": "Linux"}})
        self.assertEqual(cond("ifeq (1, $(DEVELHELP))"), {"equals": {"DEVELHELP": "1"}})
        self.assertEqual(cond("ifneq ($(DISABLE_LIBSTDCPP),1)"),
                         {"not": {"equals": {"DISABLE_LIBSTDCPP": "1"}}})
        self.assertEqual(cond("ifeq (,$(CPU))"), {"equals": {"CPU": ""}})
        self.assertEqual(cond("ifneq (,${RUST_TARGET})"),
                         {"not": {"equals": {"RUST_TARGET": ""}}})

    def test_equals_of_several_variables(self):
        self.assertEqual(cond("ifeq ($(OS) $(OS_ARCH),Linux x86_64)"),
                         {"equals": {"OS": "Linux", "OS_ARCH": "x86_64"}})

    def test_unsupported_conditions(self):
        for line in ("ifeq ($(OS) $(OS_ARCH),Linux)",          # counts differ
                     "ifneq (,$(filter $(A)x,$(B)))",           # reference inside a word
                     "ifeq (2,$(call _is_greater,$(words $(sort $(filter a,$(B)))),1))",
                     "ifeq (1,$(call _is_greater,$(words $(filter a,$(B))),1))",  # no sort
                     "ifneq (,$(findstring x,$(USEMODULE)))",   # other function
                     "ifneq (,$(filter x,$(USEMODULE) y))",     # words after the variable
                     "ifneq (,$(filter $(X)_a,$(USEMODULE)))",  # computed pattern
                     "ifeq ($(A),$(B))",                        # two variables
                     'ifeq "a" "b"',                            # quoted form
                     "ifeq (a,b,c)"):
            with self.subTest(line=line):
                with self.assertRaises(Unsupported):
                    cond(line)


class StatementTest(unittest.TestCase):

    def test_add_merges_adjacent_lines_of_one_variable(self):
        self.assertEqual(translate("USEMODULE += a\nUSEMODULE += b c\nUSEPKG += d\n"),
                         [{"add": {"USEMODULE": ["a", "b", "c"]}}, {"add": {"USEPKG": ["d"]}}])

    def test_blank_line_and_comment_stop_merging(self):
        self.assertEqual(translate("V += a\n\nV += b\n"),
                         [{"add": {"V": ["a"]}}, {"add": {"V": ["b"]}}])
        self.assertEqual(translate("V += a # why\nV += b\n"),
                         [{"comment": "why", "add": {"V": ["a"]}}, {"add": {"V": ["b"]}}])

    def test_quoted_text_is_one_item(self):
        self.assertEqual(translate('MSG += "Only one C library can be used."\n'),
                         [{"add": {"MSG": ['"Only one C library can be used."']}}])

    def test_set_flavors(self):
        self.assertEqual(translate("A = x\nB := y\nC ?= 1\n"),
                         [{"set": {"var": "A", "value": "x"}},
                          {"set": {"var": "B", "value": "y", "flavor": "simple"}},
                          {"set": {"var": "C", "value": "1", "flavor": "conditional"}}])

    def test_variable_references_become_templates(self):
        self.assertEqual(translate("FEATURES_PROVIDED += cpu_$(CPU)\n"),
                         [{"add": {"FEATURES_PROVIDED": ["cpu_${CPU}"]}}])

    def test_includes(self):
        text = ("include $(RIOTBOARD)/common/x/Makefile.dep\n"
                "-include $(APPDIR)/Makefile.$(TOOLCHAIN).dep\n"
                "-include $(PKG_PATHS:%=%Makefile.dep)\n"
                "-include $(sort $(USEMODULE:%=$(RIOTBASE)/sys/%/Makefile.dep))\n")
        self.assertEqual(translate(text), [
            {"include": {"path": "${RIOTBOARD}/common/x/Makefile.dep"}},
            {"include": {"path": "${APPDIR}/Makefile.${TOOLCHAIN}.dep", "optional": True}},
            {"include": {"for_each": "PKG_PATHS", "path": "%Makefile.dep", "optional": True}},
            {"include": {"for_each": "USEMODULE", "path": "${RIOTBASE}/sys/%/Makefile.dep",
                         "sort": True, "optional": True}}])

    def test_messages(self):
        self.assertEqual(translate("$(error $(BOARD): CPU must be defined)\n"
                                   "$(warning renamed, will be removed)\n$(info x)\n"),
                         [{"error": "${BOARD}: CPU must be defined"},
                          {"warning": "renamed, will be removed"}, {"info": "x"}])

    def test_unsupported_statements_name_file_and_line(self):
        for text in ("ifdef X\nendif\n", "define X\nendef\n", "export A = b\n",
                     "override A = b\n", "A != uname\n", "A ::= b\n", "all: x\n",
                     "A := $(shell uname)\n", "A += $(foreach m,$(B),$(m)_x)\n",
                     "$(eval A = b)\n", "include $(wildcard *.mk)\n",
                     "-include $(sort a b)\n", "else\n", "endif\n", "ifeq ($(A),b)\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(Unsupported, r"^f\.mk:[0-9]+: "):
                    translate(text, "f.mk")

    def test_unsupported_reports_the_right_line(self):
        with self.assertRaisesRegex(Unsupported, r"^f\.mk:3: "):
            translate("A = 1\n\nB := $(shell x)\n", "f.mk")


class StructureTest(unittest.TestCase):

    def test_nesting_else_and_elif(self):
        text = ("ifeq ($(C),m0)\n  A := 6\n"
                "else ifeq ($(C),m3)\n  A := 7\n"
                "else\n  $(error unknown $(C))\nendif\n"
                "ifneq (,$(filter x,$(U)))\n  ifeq (,$(filter y,$(U)))\n    U += z\n  endif\nendif\n")
        self.assertEqual(translate(text), [
            {"if": {"equals": {"C": "m0"}},
             "then": [{"set": {"var": "A", "value": "6", "flavor": "simple"}}],
             "elif": [{"if": {"equals": {"C": "m3"}},
                       "then": [{"set": {"var": "A", "value": "7", "flavor": "simple"}}]}],
             "else": [{"error": "unknown ${C}"}]},
            {"if": {"has": {"var": "U", "match": ["x"]}},
             "then": [{"if": {"not": {"has": {"var": "U", "match": ["y"]}}},
                       "then": [{"add": {"U": ["z"]}}]}]}])

    def test_tab_indented_lines_are_ordinary_lines(self):
        self.assertEqual(translate("ifneq (,$(filter a,$(U)))\n\tU += b\nendif\n"),
                         [{"if": {"has": {"var": "U", "match": ["a"]}},
                           "then": [{"add": {"U": ["b"]}}]}])

    def test_comments(self):
        text = ("# header\n#\n# more\n\n# about A\nA = 1 # trailing\n"
                "ifneq (,$(filter a,$(U)))\n  # inside\nendif\n# at the end\n")
        self.assertEqual(translate(text), [
            {"comment": "header\n\nmore"},
            {"comment": "about A\ntrailing", "set": {"var": "A", "value": "1"}},
            {"if": {"has": {"var": "U", "match": ["a"]}}, "then": [{"comment": "inside"}]},
            {"comment": "at the end"}])

    def test_continuation_lines_are_joined(self):
        self.assertEqual(translate("U += a \\\n     b\n"), [{"add": {"U": ["a", "b"]}}])

    def test_else_after_else_is_rejected(self):
        with self.assertRaises(Unsupported):
            translate("ifeq ($(A),1)\nelse\nelse\nendif\n")

    def test_missing_endif_is_rejected(self):
        with self.assertRaisesRegex(Unsupported, "missing endif"):
            translate("ifeq ($(A),1)\n")


if __name__ == "__main__":
    unittest.main()
