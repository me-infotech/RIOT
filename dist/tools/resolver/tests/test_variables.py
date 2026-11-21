#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""V1: variables of the data behave like the Make variables the generated
adapters assign (flavors, command line, selections, patterns).

Run: python3 -m unittest discover -s dist/tools/resolver/tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from variables import Variables, drop, keep, matches, sort  # noqa: E402


class PatternTest(unittest.TestCase):

    def test_positive_and_negative_samples(self):
        for pattern, word, result in (("periph_%", "periph_uart", True),
                                      ("periph_%", "periph_", True),       # % may be empty
                                      ("%_init", "auto_init", True),
                                      ("a%b", "ab", True),
                                      ("periph_%", "xperiph_uart", False),
                                      ("a%b", "a", False),                 # prefix and suffix overlap
                                      ("uart", "uart", True),
                                      ("uart", "uart0", False),
                                      ("uart", "", False)):
            with self.subTest(pattern=pattern, word=word):
                self.assertIs(matches(pattern, word), result)

    def test_keep_drop_sort(self):
        words = ["b", "a1", "c", "a1", "a2"]
        self.assertEqual(keep(["a%"], words), ["a1", "a1", "a2"])
        self.assertEqual(drop(["a%", "c"], words), ["b"])
        self.assertEqual(sort(words), ["a1", "a2", "b", "c"])


class FlavorTest(unittest.TestCase):

    def test_recursive_is_expanded_when_used(self):
        v = Variables()
        v.set("A", "x_${B}")
        v.set("B", "1")
        self.assertEqual(v.get("A"), "x_1")
        v.set("B", "2")
        self.assertEqual(v.get("A"), "x_2")

    def test_simple_is_expanded_when_assigned(self):
        v = Variables()
        v.set("B", "1")
        v.set("A", "x_${B}", "simple")
        v.set("B", "2")
        self.assertEqual(v.get("A"), "x_1")

    def test_add_keeps_the_flavor(self):
        v = Variables()
        v.set("B", "1")
        v.set_words("S", ["s"])
        v.add("S", "${B}")
        v.add("R", "${B}")            # undefined: becomes recursive
        v.set("B", "2")
        self.assertEqual((v.get("S"), v.flavor("S")), ("s 1", "simple"))
        self.assertEqual((v.get("R"), v.flavor("R")), ("2", "recursive"))

    def test_conditional_only_if_undefined(self):
        v = Variables()
        v.set("A", "1", "conditional")
        v.set("A", "2", "conditional")
        v.set("E", "")
        v.set("E", "3", "conditional")   # defined, even if empty
        self.assertEqual((v.get("A"), v.get("E")), ("1", ""))

    def test_command_line_wins_over_the_data(self):
        v = Variables()
        v.command_line("BOARD", "nrf52840dk")
        v.set("BOARD", "native", "conditional")
        v.set("BOARD", "native")
        v.set_words("BOARD", ["native"])
        v.add("BOARD", "x")
        self.assertEqual(v.get("BOARD"), "nrf52840dk")
        self.assertEqual(v.get("UNDEFINED"), "")

    def test_add_to_a_recursive_variable_keeps_the_reference(self):
        v = Variables()
        v.set("R", "a")
        v.add("R", "${B}")
        v.add("R", {"select": {"var": "C", "match": ["c%"]}})
        v.set("B", "b")
        v.set_words("C", ["c1", "x"])
        self.assertEqual(v.words("R"), ["a", "b", "c1"])

    def test_selection_in_a_recursive_value_follows_its_variable(self):
        """FEATURES_REQUIRED += $(filter-out $(IGNORE),$(filter periph_%,$(USEMODULE)))
        sees the modules and the ignore list of the moment it is used."""
        v = Variables()
        v.add("REQ", {"select": {"var": "USEMODULE", "match": ["periph_%"],
                                 "except": ["${IGNORE}"]}})
        v.set_words("USEMODULE", ["periph_uart", "core"])
        self.assertEqual(v.words("REQ"), ["periph_uart"])
        v.set_words("USEMODULE", ["periph_uart", "periph_spi"])
        v.set_words("IGNORE", ["periph_uart"])
        self.assertEqual(v.words("REQ"), ["periph_spi"])


class SelectTest(unittest.TestCase):

    def setUp(self):
        self.v = Variables()
        self.v.set_words("USEMODULE", ["periph_uart", "periph_init_x", "core", "periph_gpio"])
        self.v.set_words("IGNORE", ["periph_init%", "periph_gpio"])

    def test_match_except_and_reference_patterns(self):
        sel = {"var": "USEMODULE", "match": ["periph_%"], "except": ["${IGNORE}"]}
        self.assertEqual(self.v.select(sel), ["periph_uart"])
        self.assertEqual(self.v.select({"var": "USEMODULE"}), self.v.words("USEMODULE"))
        self.assertEqual(self.v.select({"var": "USEMODULE", "match": ["nothing"]}), [])

    def test_replace_every_occurrence(self):
        self.v.set_words("P", ["periph_uart", "periph_periph_x"])
        sel = {"var": "P", "replace": {"from": "periph_", "to": "periph_init_"}}
        self.assertEqual(self.v.select(sel), ["periph_init_uart", "periph_init_periph_init_x"])


if __name__ == "__main__":
    unittest.main()
