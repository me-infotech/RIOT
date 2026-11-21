#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""S1-S4 (step G0-2): schema 2, the extension for the rule files of the
build system pipeline - `select` values, `${NAME}` as a whole pattern word
and the `several` condition - in validator, translator, generator and
normal form; file names of the new kinds of data.

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOL)

# pylint: disable=wrong-import-position
import generate  # noqa: E402
import rules as R  # noqa: E402
import schema  # noqa: E402
from translate import Unsupported, condition, translate  # noqa: E402

SEL = {"var": "USEMODULE", "match": ["periph_%"], "except": ["${IGNORE}"]}
VALID2 = {"schema": 2, "rules": [
    {"if": {"several": {"var": "USEMODULE", "match": ["${STDIO_MODULES}"]}},
     "then": [{"add": {"USEMODULE": ["stdio_dispatch"]}}]},
    {"if": {"not": {"has": {"var": "USEMODULE", "match": ["${LEGACY}"]}}},
     "then": [{"add": {"USEMODULE": ["stdio"]}}]},
    {"set": {"var": "PERIPH", "value": {"select": SEL}, "flavor": "simple"}},
    {"set": {"var": "INIT", "value": {"select": {
        "var": "PERIPH", "replace": {"from": "periph_", "to": "periph_init_"}}},
        "flavor": "simple"}},
    {"add": {"USEMODULE": [{"select": {"var": "FEATURES_USED", "match": ["vdd_lc_%"]}},
                           "plain"]}},
]}


def cond(line: str) -> dict:
    kind, args = line.split(None, 1)
    return condition(kind, args)


class ValidatorTest(unittest.TestCase):
    """S1: schema 2 accepts the new constructs, rejects broken ones and
    keeps schema 1 strict."""

    def test_schema2_sample_is_valid(self):
        self.assertEqual(schema.validate(VALID2), [])
        self.assertEqual(R.needed_schema(VALID2["rules"]), 2)

    def test_schema1_document_must_not_use_schema2(self):
        for i in range(len(VALID2["rules"])):
            with self.subTest(rule=i):
                doc = {"schema": 1, "rules": [VALID2["rules"][i]]}
                self.assertIn("schema: the rules need schema 2", schema.validate(doc))

    def test_schema1_rules_need_schema1(self):
        rules = [{"if": {"has": {"var": "A", "match": ["x%"]}}, "then": [{"add": {"B": ["c"]}}]}]
        self.assertEqual(R.needed_schema(rules), 1)
        self.assertEqual(schema.validate({"schema": 2, "rules": rules}), [])

    def test_negative_samples(self):
        def with_value(value):
            doc = copy.deepcopy(VALID2)
            doc["rules"][2]["set"]["value"] = value
            return doc
        cases = [
            (with_value({"select": {**SEL, "match": ["$(X)"]}}), "is not a pattern"),
            (with_value({"select": {**SEL, "match": ["a${X}"]}}), "is not a pattern"),
            (with_value({"select": {"match": ["a"]}}), "missing key 'var'"),
            (with_value({"select": {**SEL, "sort": True}}), "unknown key 'sort'"),
            (with_value({"pick": SEL}), "missing key 'select'"),
            (with_value({"select": {"var": "A", "replace": {"from": "", "to": "x"}}}),
             "from: must not be empty"),
            (with_value({"select": {"var": "A", "replace": {"from": "a b", "to": "x"}}}),
             "is not a literal text"),
            (with_value({"select": {"var": "A", "replace": {"from": "a"}}}), "missing key 'to'"),
            ({"schema": 2, "rules": [{"if": {"several": {"var": "A"}}, "then": []}]},
             "missing key 'match'"),
            ({"schema": 2, "rules": [{"if": {"several": {"var": "A", "match": ["x"],
                                                         "count": 2}}, "then": []}]},
             "unknown key 'count'"),
        ]
        for doc, text in cases:
            with self.subTest(text=text):
                problems = schema.validate(doc)
                self.assertTrue(any(text in p for p in problems), problems)


class TranslatorTest(unittest.TestCase):
    """S2: the translator reads the Make forms of the pipeline files."""

    def test_reference_as_pattern_word(self):
        self.assertEqual(cond("ifeq (,$(filter $(LEGACY),$(USEMODULE)))"),
                         {"not": {"has": {"var": "USEMODULE", "match": ["${LEGACY}"]}}})

    def test_several(self):
        line = "ifeq (1, $(call _is_greater,$(words $(sort $(filter $(M),$(USEMODULE)))),1))"
        self.assertEqual(cond(line), {"several": {"var": "USEMODULE", "match": ["${M}"]}})
        self.assertEqual(cond(line.replace("ifeq", "ifneq", 1)),
                         {"not": {"several": {"var": "USEMODULE", "match": ["${M}"]}}})

    def test_select_values(self):
        rules = translate("A := $(filter-out $(IGNORE),$(filter periph_%,$(USEMODULE)))\n"
                          "B := $(subst periph_,periph_init_,$(A))\n"
                          "USEMODULE += $(filter vdd_lc_%, $(FEATURES_USED))\n")
        self.assertEqual(rules, [
            {"set": {"var": "A", "value": {"select": {"var": "USEMODULE", "match": ["periph_%"],
                                                      "except": ["${IGNORE}"]}},
                     "flavor": "simple"}},
            {"set": {"var": "B", "value": {"select": {
                "var": "A", "replace": {"from": "periph_", "to": "periph_init_"}}},
                "flavor": "simple"}},
            {"add": {"USEMODULE": [{"select": {"var": "FEATURES_USED",
                                               "match": ["vdd_lc_%"]}}]}}])

    def test_string_helpers_only_first_and_only_for_several(self):
        several = "ifeq (1,$(call _is_greater,$(words $(sort $(filter a b,$(V)))),1))\nendif\n"
        helpers = "include $(RIOTMAKE)/utils/strings.mk\n"
        self.assertEqual(translate("# head\n\n" + helpers + several),
                         [{"comment": "head"},
                          {"if": {"several": {"var": "V", "match": ["a", "b"]}}, "then": []}])
        for text in (helpers + "A = 1\n",                       # no `several`
                     "A = 1\n" + helpers + several):            # not first
            with self.subTest(text=text):
                with self.assertRaises(Unsupported):
                    translate(text)

    def test_unsupported_values(self):
        for line in ("A := $(subst a,b,$(filter x,$(V)) y)",    # words after the selection
                     "A := $(subst $(X),b,$(V))",               # computed text
                     "A := $(subst a,b,$(sort $(V)))",          # other function inside
                     "A += $(filter a,$(V) $(W))"):             # two variables
            with self.subTest(line=line):
                with self.assertRaises(Unsupported):
                    translate(line + "\n")


class GeneratorTest(unittest.TestCase):
    """S3: the Make text of the new constructs; `several` brings the helpers."""

    def test_condition_texts(self):
        self.assertEqual(generate.condition({"several": {"var": "V", "match": ["${M}"]}}),
                         "ifeq (1,$(call _is_greater,$(words $(sort $(filter $(M),$(V)))),1))")
        self.assertEqual(generate.condition({"not": {"has": {"var": "V", "match": ["${L}"]}}}),
                         "ifeq (,$(filter $(L),$(V)))")

    def test_value_texts(self):
        self.assertEqual(generate.value_text({"select": SEL}),
                         "$(filter periph_%,$(filter-out $(IGNORE),$(USEMODULE)))")
        self.assertEqual(generate.value_text({"select": {"var": "A", "replace": {
            "from": "periph_", "to": "periph_init_"}}}), "$(subst periph_,periph_init_,$(A))")

    def test_helpers_only_with_several(self):
        text = generate.make_text(VALID2["rules"], "x.inc.yaml")
        self.assertEqual(text.split("\n")[3], generate.STRING_HELPERS)
        text = generate.make_text(VALID2["rules"][1:], "x.inc.yaml")
        self.assertNotIn("strings.mk", text)

    def test_round_trip_of_the_sample(self):
        text = generate.make_text(VALID2["rules"], "x.inc.yaml")
        self.assertEqual(R.normalise(translate(text)), R.normalise(VALID2["rules"]))


class NormalFormTest(unittest.TestCase):
    """S4: the normal form sees a change inside a selection."""

    def test_changed_selection_is_found(self):
        other = copy.deepcopy(VALID2["rules"])
        other[3]["set"]["value"]["select"]["replace"]["to"] = "periph_x_"
        self.assertNotEqual(R.normalise(other), R.normalise(VALID2["rules"]))
        other = copy.deepcopy(VALID2["rules"])
        other[2]["set"]["value"]["select"]["except"] = []
        self.assertNotEqual(R.normalise(other), R.normalise(VALID2["rules"]))

    def test_empty_except_is_no_except(self):
        sel = {"select": {"var": "A", "match": ["x"]}}
        with_empty = {"select": {"var": "A", "match": ["x"], "except": []}}
        self.assertEqual(R.normalise([{"add": {"B": [sel]}}]),
                         R.normalise([{"add": {"B": [with_empty]}}]))


class FileNameTest(unittest.TestCase):

    def test_pipeline_and_application_names(self):
        for make, data in (("makefiles/stdio.inc.mk", "makefiles/stdio.inc.yaml"),
                           ("examples/x/Makefile", "examples/x/riot-app.yaml"),
                           ("boards/b/Makefile.default", "boards/b/default.yaml")):
            with self.subTest(make=make):
                self.assertEqual(R.yaml_name(make), data)
                self.assertEqual(R.make_name(data), make)
                self.assertTrue(R.is_yaml_name(data))
        for name in ("Makefile.include", "x.yaml", ".inc.yaml"):
            with self.subTest(name=name):
                self.assertFalse(R.is_yaml_name(name))


class AdapterTest(unittest.TestCase):
    """S5: the new generated Make files (pipeline rules, application
    Makefile) are checked like the others: a copy is up to date, a changed
    YAML or a hand-edited Make file is reported."""

    def check(self, *files):
        return subprocess.run([sys.executable, os.path.join(TOOL, "config_data.py"), "generate",
                               "--check", *files], capture_output=True, text=True, check=False)

    def test_copies(self):
        for directory, data, make, old, new in (
                ("makefiles", "stdio.inc.yaml", "stdio.inc.mk", "match: [stdio_rtt]",
                 "match: [stdio_rtc]"),
                ("examples/basic/hello-world", "riot-app.yaml", "Makefile", "value: '1'",
                 "value: '0'")):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                for name in (data, make):
                    shutil.copy(os.path.join(R.RIOTBASE, directory, name), tmp)
                self.assertEqual(self.check(os.path.join(tmp, data)).returncode, 0)
                path = os.path.join(tmp, data)
                with open(path, encoding="utf-8") as file:
                    text = file.read()
                self.assertIn(old, text)
                with open(path, "w", encoding="utf-8") as file:
                    file.write(text.replace(old, new, 1))
                result = self.check(path)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"is not up to date with {data}", result.stderr)


if __name__ == "__main__":
    unittest.main()
