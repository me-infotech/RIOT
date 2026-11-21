#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C1: the validator accepts the structured format and finds each kind of
problem, above all any Make syntax in the data (negative samples).

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import copy
import os
import sys
import unittest

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOL)

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import rules as R  # noqa: E402
import schema  # noqa: E402

VALID = {"schema": 1, "rules": [
    {"comment": "every construct once"},
    {"if": {"has": {"var": "USEMODULE", "match": ["gnrc_%"], "except": ["gnrc_netif%"]}},
     "then": [{"add": {"USEMODULE": ["gnrc", "cpu_${CPU}"]}}]},
    {"if": {"not": {"selection_equals": {"var": "USEMODULE", "match": ["a", "b"],
                                         "words": ["b"]}}},
     "then": [], "else": [{"add": {"USEMODULE": ["c"]}}]},
    {"if": {"one_of": {"var": "CPU_CORE", "values": ["m4f", "m7"]}},
     "then": [{"set": {"var": "A", "value": "x", "flavor": "simple"}}],
     "elif": [{"comment": "c", "if": {"equals": {"OS": "Linux", "OS_ARCH": "x86_64"}},
               "then": [{"set": {"var": "B", "value": ""}}]}],
     "else": [{"error": "${BOARD}: unknown (core)"}]},
    {"if": {"equals": {"CPU": ""}}, "then": [{"warning": "w"}, {"info": "i"}]},
    {"include": {"path": "${RIOTBOARD}/x/Makefile.dep", "optional": True}},
    {"include": {"for_each": "USEMODULE", "path": "${RIOTBASE}/sys/%/Makefile.dep",
                 "sort": True, "optional": True}},
    {"add": {"MSG": ['"Only one C library can be used."']}},
]}


def changed(path, value):
    """VALID with the value at path (list of keys/indices) replaced; a value
    of DELETE removes the key."""
    doc = copy.deepcopy(VALID)
    node = doc
    for key in path[:-1]:
        node = node[key]
    if value is DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return doc


DELETE = object()


class ValidDocumentTest(unittest.TestCase):

    def test_sample_with_every_construct_is_valid(self):
        self.assertEqual(schema.validate(VALID), [])

    def test_every_yaml_of_the_repository_is_valid(self):
        files = config_data.all_yaml()
        self.assertGreater(len(files), 0)
        for path in files:
            with self.subTest(path=config_data.rel(path)):
                self.assertEqual(schema.validate(R.load_yaml(path)), [])


class InvalidDocumentTest(unittest.TestCase):
    """Negative samples: each must produce the named problem."""

    CASES = [
        # (path, new value, expected text in a problem)
        (["schema"], 4, "schema: must be one of 1, 2, 3"),
        (["rules"], {}, "must be a list"),
        (["extra"], 1, "unknown key 'extra'"),
        (["rules", 1, "if", "has", "match"], ["$(X)_a"], "is not a pattern"),
        (["rules", 1, "if", "has", "match"], ["a%b%"], "is not a pattern"),
        (["rules", 1, "if", "has", "match"], [], "non-empty list"),
        (["rules", 1, "if", "has", "var"], "$(USEMODULE)", "not a variable name"),
        (["rules", 1, "if", "has", "except"], ["a b"], "is not a pattern"),
        (["rules", 1, "if", "has", "expr"], "x", "unknown key 'expr'"),
        (["rules", 1, "if"], {"make_expr": "$(filter a,$(U))"}, "unknown condition"),
        (["rules", 1, "if"], {"has": {"var": "U", "match": ["a"]}, "one_of": {}},
         "a condition is a mapping with one of"),
        (["rules", 2, "if", "not"], {"not": {"equals": {"A": "1"}}}, "`not` inside `not`"),
        (["rules", 3, "if", "one_of", "values"], ["m%"], "is not a word"),
        (["rules", 3, "elif", 0, "if", "equals", "OS"], "Linux x", "one non-empty word"),
        (["rules", 4, "if", "equals", "CPU"], "$(X)", "not a literal value"),
        (["rules", 3, "elif"], [], "non-empty list"),
        (["rules", 3, "elif", 0, "then"], DELETE, "missing key 'then'"),
        (["rules", 1, "then", 0, "add", "USEMODULE"], ["$(filter a,$(B))"], "`$` is only"),
        (["rules", 1, "then", 0, "add", "USEMODULE"], ["a # b"], "`#` is not allowed"),
        (["rules", 1, "then", 0, "add", "USEMODULE"], [], "non-empty list"),
        (["rules", 1, "then", 0, "add"], {"A": ["x"], "B": ["y"]}, "one variable"),
        (["rules", 3, "then", 0, "set", "value"], "$(shell uname)", "`$` is only"),
        (["rules", 3, "then", 0, "set", "flavor"], "lazy", "flavor: one of"),
        (["rules", 3, "else", 0, "error"], "unbalanced (", "parentheses must be balanced"),
        (["rules", 3, "else", 0, "error"], "", "must not be empty"),
        (["rules", 5, "include", "path"], "$(wildcard *.dep)", "`$` is only"),
        (["rules", 5, "include", "path"], "a/%/b", "`%` only with for_each"),
        (["rules", 5, "include", "sort"], True, "only with for_each"),
        (["rules", 5, "include", "optional"], "yes", "true or false"),
        (["rules", 6, "include", "path"], "${RIOTBASE}/sys/Makefile.dep", "exactly one `%`"),
        (["rules", 6, "include", "for_each"], "$(USEMODULE)", "not a variable name"),
        (["rules", 0, "then"], [], "then/elif/else only with if"),
        (["rules", 5, "then"], [], "then/elif/else only with if"),
        (["rules", 1, "then"], DELETE, "if without then"),
        (["rules", 7], {"add": {"A": ["x"]}, "set": {"var": "B", "value": "y"}},
         "more than one action"),
        (["rules", 7], {"make": "A += b"}, "unknown key 'make'"),
        (["rules", 7], {}, "no action"),
        (["rules", 7], "A += b", "must be a mapping"),
        (["rules", 0, "comment"], 3, "comment: must be a string"),
    ]

    def test_negative_samples(self):
        for path, value, text in self.CASES:
            with self.subTest(path=path, value=value):
                problems = schema.validate(changed(path, value))
                self.assertTrue(any(text in p for p in problems), f"{text!r} not in {problems}")

    def test_problem_names_the_path(self):
        problems = schema.validate(changed(["rules", 1, "then", 0, "add", "USEMODULE"], ["$(X)"]))
        self.assertIn("rules[1].then[0].add.USEMODULE[0]", problems[0])

    def test_not_a_mapping(self):
        self.assertEqual(schema.validate([]), ["document: must be a mapping with schema and rules"])


if __name__ == "__main__":
    unittest.main()
