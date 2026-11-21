#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""E1: the rules of the data are evaluated like the generated Make files
(each condition with a positive and a negative sample, branches, actions);
E2: includes read the YAML next to the named Make file, run the hooks of
the algorithm, skip Make-only files and report what the data does not
cover.

Run: python3 -m unittest discover -s dist/tools/resolver/tests -v
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
import yaml  # noqa: E402
from evaluate import MAKE_ONLY, Evaluator, OutOfScope, ResolveError, RIOTBASE  # noqa: E402
from variables import Variables  # noqa: E402


def evaluator(**words) -> Evaluator:
    v = Variables()
    for name, value in words.items():
        v.set_words(name, value.split())
    return Evaluator(v, RIOTBASE)


class ConditionTest(unittest.TestCase):

    def test_positive_and_negative_samples(self):
        ev = evaluator(USEMODULE="gnrc_ipv6 gnrc_netif stdio_uart stdio_rtt",
                       STDIO="stdio_uart stdio_rtt stdio_null", CPU_CORE="cortex-m4f",
                       OS="Linux", OS_ARCH="x86_64", EMPTY="", ONE="stdio_uart stdio_uart")
        cases = [
            ({"has": {"var": "USEMODULE", "match": ["gnrc_%"]}}, True),
            ({"has": {"var": "USEMODULE", "match": ["gnrc_%"],
                      "except": ["gnrc_ipv6", "gnrc_netif"]}}, False),
            ({"has": {"var": "USEMODULE", "match": ["${STDIO}"]}}, True),
            ({"several": {"var": "USEMODULE", "match": ["${STDIO}"]}}, True),
            ({"several": {"var": "ONE", "match": ["${STDIO}"]}}, False),   # one distinct word
            ({"several": {"var": "EMPTY", "match": ["%"]}}, False),
            ({"selection_equals": {"var": "USEMODULE", "match": ["stdio_rtt", "stdio_null"],
                                   "words": ["stdio_rtt"]}}, True),
            ({"selection_equals": {"var": "USEMODULE", "match": ["stdio_%"],
                                   "words": ["stdio_rtt"]}}, False),
            ({"one_of": {"var": "CPU_CORE", "values": ["cortex-m4f", "cortex-m7"]}}, True),
            ({"one_of": {"var": "CPU_CORE", "values": ["cortex-m0"]}}, False),
            ({"one_of": {"var": "EMPTY", "values": ["x"]}}, False),
            ({"equals": {"OS": "Linux", "OS_ARCH": "x86_64"}}, True),
            ({"equals": {"OS": "Linux", "OS_ARCH": "arm64"}}, False),
            ({"equals": {"EMPTY": ""}}, True),
            ({"equals": {"OS": ""}}, False),
            ({"not": {"equals": {"OS": ""}}}, True),
        ]
        for cond, result in cases:
            with self.subTest(cond=cond):
                self.assertIs(ev.condition(cond), result)


class RuleTest(unittest.TestCase):

    def test_branches_in_order(self):
        rules = [{"if": {"equals": {"X": "2"}}, "then": [{"add": {"OUT": ["then"]}}],
                  "elif": [{"if": {"equals": {"X": "3"}}, "then": [{"add": {"OUT": ["elif3"]}}]},
                           {"if": {"equals": {"Y": "1"}}, "then": [{"add": {"OUT": ["elifY"]}}]}],
                  "else": [{"add": {"OUT": ["else"]}}]}]
        for x, y, out in (("2", "1", "then"), ("3", "1", "elif3"), ("4", "1", "elifY"),
                          ("4", "0", "else")):
            with self.subTest(x=x, y=y):
                ev = evaluator(X=x, Y=y)
                ev.run(rules)
                self.assertEqual(ev.v.get("OUT"), out)

    def test_later_rules_see_earlier_ones(self):
        ev = evaluator(USEMODULE="a")
        ev.run([{"if": {"has": {"var": "USEMODULE", "match": ["a"]}},
                 "then": [{"add": {"USEMODULE": ["b"]}}]},
                {"if": {"has": {"var": "USEMODULE", "match": ["b"]}},
                 "then": [{"add": {"USEMODULE": ["c"]}}]}])
        self.assertEqual(ev.v.words("USEMODULE"), ["a", "b", "c"])

    def test_messages(self):
        ev = evaluator(BOARD="b")
        ev.run([{"warning": "w ${BOARD}"}, {"info": "i"}])
        self.assertEqual(ev.messages, [("warning", "w b"), ("info", "i")])
        with self.assertRaisesRegex(ResolveError, "where: b: CPU must be defined"):
            ev.run([{"error": "${BOARD}: CPU must be defined"}], "where")


class IncludeTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.ev = Evaluator(Variables(), self.dir)
        self.ev.v.set_words("D", [self.dir])

    def write(self, name, content):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(content if isinstance(content, str) else yaml.safe_dump(content))
        return path

    def test_reads_the_yaml_next_to_the_make_file(self):
        self.write("x/deps.yaml", {"schema": 1, "rules": [{"add": {"USEMODULE": ["x"]}}]})
        self.ev.run([{"include": {"path": "${D}/x/Makefile.dep"}}])
        self.assertEqual(self.ev.v.words("USEMODULE"), ["x"])

    def test_for_each_sorted(self):
        for name in ("b", "a"):
            self.write(f"{name}/deps.yaml",
                       {"schema": 1, "rules": [{"add": {"ORDER": [name]}}]})
        self.ev.v.set_words("USEMODULE", ["b", "a", "b", "missing"])
        self.ev.run([{"include": {"for_each": "USEMODULE", "path": "${D}/%/Makefile.dep",
                                  "sort": True, "optional": True}}])
        self.assertEqual(self.ev.v.words("ORDER"), ["a", "b"])

    def test_optional_missing_file_is_skipped_and_required_one_is_an_error(self):
        self.ev.run([{"include": {"path": "${D}/none/Makefile.dep", "optional": True}}])
        with self.assertRaisesRegex(ResolveError, "no such file"):
            self.ev.run([{"include": {"path": "${D}/none/Makefile.dep"}}])

    def test_make_file_without_data_is_outside_the_scope(self):
        self.write("y/Makefile.dep", "USEMODULE += y\n")
        for optional in (False, True):
            with self.subTest(optional=optional):
                with self.assertRaisesRegex(OutOfScope, "not converted to data"):
                    self.ev.run([{"include": {"path": "${D}/y/Makefile.dep",
                                              "optional": optional}}])

    def test_invalid_yaml_is_an_error(self):
        self.write("z/deps.yaml", {"schema": 1, "rules": [{"add": {"USEMODULE": ["$(X)"]}}]})
        with self.assertRaisesRegex(ResolveError, "only allowed in a reference"):
            self.ev.run([{"include": {"path": "${D}/z/Makefile.dep"}}])

    def test_hooks_and_make_only_files(self):
        calls = []
        self.ev.hooks["makefiles/features_check.inc.mk"] = lambda: calls.append(1)
        self.ev.v.set_words("RIOTMAKE", [os.path.join(RIOTBASE, "makefiles")])
        self.ev.run([{"include": {"path": "${RIOTMAKE}/features_check.inc.mk"}},
                     {"include": {"path": "${RIOTMAKE}/default-radio-settings.inc.mk"}}])
        self.assertEqual(calls, [1])
        self.assertEqual(self.ev.skipped, ["makefiles/default-radio-settings.inc.mk"])
        self.assertEqual(list(MAKE_ONLY), ["makefiles/default-radio-settings.inc.mk"])


if __name__ == "__main__":
    unittest.main()
