# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""S1-S4: schema 3 of the data format (step G3-1) - validator, generator,
translator, names of the module data - and the data files of the step."""

import os
import subprocess
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
import buildeval  # noqa: E402,F401  (sets sys.path for config_data, resolver)
import generate  # noqa: E402
import rules as R  # noqa: E402
import schema  # noqa: E402
import translate  # noqa: E402

RIOTBASE = R.RIOTBASE


def doc(*rules):
    return {"schema": 3, "rules": list(rules)}


def setv(value):
    return {"set": {"var": "X", "value": value}}


class ValidatorTest(unittest.TestCase):
    """S1: schema 3 constructs are accepted, malformed ones rejected."""

    VALID = [
        setv({"files": {"match": ["*.c"]}}),
        setv({"files": {"match": ["${DIR}/include"], "except": ["init.c", "x%"]}}),
        setv({"subdirs": {"select": {"var": "USEMODULE", "except": ["${FILTER}"]},
                          "file": "Makefile"}}),
        setv({"select": {"var": "A", "pattern": {"from": "%.c", "to": "periph_%"}}}),
        setv({"select": {"var": "A", "pattern": {"from": "${P}%.c", "to": "%"}}}),
        setv({"select": {"var": "A", "macro": True, "unique": True}}),
        setv({"arith": {"expr": "${ROM_LEN}-${SLOT_AUX_LEN}"}}),
        setv({"arith": {"expr": "(1024K)*2", "format": "hex"}}),
        {"if": {"at_least": {"var": "GCC_VERSION", "version": "8"}}, "then": []},
        {"if": {"not": {"at_least": {"var": "V", "version": "4.2.1"}}}, "then": []},
        {"if": {"nonempty": ["A", "B"]}, "then": []},
        {"add": {"CFLAGS": [{"files": {"match": ["*.c"]}}]}},
    ]
    INVALID = [
        (setv({"files": {"match": ["$(wildcard *.c)"]}}), "is not a file pattern"),
        (setv({"files": {}}), "missing key 'match'"),
        (setv({"files": {"match": ["*.c"], "sort": True}}), "unknown key 'sort'"),
        (setv({"subdirs": {"select": {"var": "U"}, "file": "a/Makefile"}}),
         "must be a file name"),
        (setv({"subdirs": {"select": {"var": "U"}}}), "missing key 'file'"),
        (setv({"select": {"var": "A", "pattern": {"from": "x.c", "to": "y"}}}),
         "needs exactly one `%`"),
        (setv({"select": {"var": "A", "pattern": {"from": "a b%", "to": "y"}}}),
         "is not a pattern word"),
        (setv({"select": {"var": "A", "macro": "yes"}}), "must be true or false"),
        (setv({"arith": {"expr": "$(shell echo 1)"}}), "is not an expression"),
        (setv({"arith": {"expr": "1", "format": "oct"}}), "dec or hex"),
        (setv({"files": {"match": ["*.c"]}, "select": {"var": "A"}}), "exactly one key"),
        (setv({"pick": {"var": "A"}}), "unknown value 'pick'"),
        ({"if": {"at_least": {"var": "V", "version": "8.x"}}, "then": []}, "a version like"),
        ({"if": {"at_least": {"var": "V"}}, "then": []}, "missing key 'version'"),
        ({"if": {"nonempty": []}, "then": []}, "non-empty list"),
        ({"if": {"nonempty": ["$(A)"]}, "then": []}, "is not a variable name"),
    ]

    def test_valid_constructs(self):
        for rule in self.VALID:
            with self.subTest(rule=rule):
                self.assertEqual(schema.validate(doc(rule)), [])

    def test_invalid_constructs(self):
        for rule, text in self.INVALID:
            with self.subTest(text=text):
                problems = schema.validate(doc(rule))
                self.assertTrue(any(text in p for p in problems), problems)

    def test_schema_3_constructs_need_schema_3(self):
        for rule in self.VALID:
            with self.subTest(rule=rule):
                self.assertEqual(R.needed_schema([rule]), 3)
                problems = schema.validate({"schema": 2, "rules": [rule]})
                self.assertIn("schema: the rules need schema 3", problems)

    def test_schema_1_and_2_documents_stay_valid(self):
        self.assertEqual(R.needed_schema([{"add": {"USEMODULE": ["a"]}}]), 1)
        self.assertEqual(R.needed_schema([setv({"select": {"var": "A", "match": ["b"]}})]), 2)


class GeneratorTest(unittest.TestCase):
    """S2: Make text of the schema 3 constructs (the generated adapters)."""

    def text(self, value):
        return generate.value_text(value)

    def test_values(self):
        cases = [
            ({"files": {"match": ["*.c"]}}, "$(wildcard *.c)"),
            ({"files": {"match": ["*.c"], "except": ["a.c", "b.c"]}},
             "$(filter-out a.c b.c,$(wildcard *.c))"),
            ({"files": {"match": ["${P}*.c"]}}, "$(wildcard $(P)*.c)"),
            ({"subdirs": {"select": {"var": "USEMODULE"}, "file": "Makefile"}},
             "$(dir $(wildcard $(addsuffix /Makefile,$(USEMODULE))))"),
            ({"subdirs": {"select": {"var": "U", "except": ["${F}"]}, "file": "Makefile"}},
             "$(dir $(wildcard $(addsuffix /Makefile,$(filter-out $(F),$(U)))))"),
            ({"select": {"var": "A", "pattern": {"from": "%.c", "to": "periph_%"}}},
             "$(patsubst %.c,periph_%,$(A))"),
            ({"select": {"var": "U", "match": ["${M}"], "pattern": {"from": "p_%", "to": "%.c"}}},
             "$(patsubst p_%,%.c,$(filter $(M),$(U)))"),
            ({"select": {"var": "B", "macro": True}}, "$(call uppercase_and_underscore,$(B))"),
        ]
        for value, text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.text(value), text)

    def test_conditions(self):
        self.assertEqual(generate.condition({"at_least": {"var": "V", "version": "8"}}),
                         "ifeq (1,$(call version_is_greater_or_equal,$(V),8))")
        self.assertEqual(generate.condition({"not": {"at_least": {"var": "V", "version": "8"}}}),
                         "ifneq (1,$(call version_is_greater_or_equal,$(V),8))")
        self.assertEqual(generate.condition({"nonempty": ["A", "B"]}), "ifneq (,$(A)$(B))")

    def test_build_only_constructs_are_not_written_as_make(self):
        for value in ({"arith": {"expr": "1"}}, {"select": {"var": "A", "unique": True}}):
            with self.subTest(value=value):
                with self.assertRaises(generate.NotForMake):
                    self.text(value)


class TranslatorTest(unittest.TestCase):
    """S3: the translator reads the Make forms of the module Makefiles, and
    generated text translates back to the same rules."""

    CASES = [
        ("SRC := $(filter-out a.c b.c,$(wildcard *.c))",
         {"set": {"var": "SRC", "value": {"files": {"match": ["*.c"], "except": ["a.c", "b.c"]}},
                  "flavor": "simple"}}),
        ("X = $(wildcard $(P)*.c)",
         {"set": {"var": "X", "value": {"files": {"match": ["${P}*.c"]}}}}),
        ("DIRS += $(dir $(wildcard $(addsuffix /Makefile, $(USEMODULE))))",
         {"add": {"DIRS": [{"subdirs": {"select": {"var": "USEMODULE"}, "file": "Makefile"}}]}}),
        ("DIRS += $(dir $(wildcard $(addsuffix /Makefile, $(filter-out $(F), $(U)))))",
         {"add": {"DIRS": [{"subdirs": {"select": {"var": "U", "except": ["${F}"]},
                                        "file": "Makefile"}}]}}),
        ("X = $(patsubst %.c,p_%,$(A))",
         {"set": {"var": "X", "value": {"select": {"var": "A",
                                                   "pattern": {"from": "%.c", "to": "p_%"}}}}}),
    ]

    def test_make_forms(self):
        for text, rule in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(translate.translate(text + "\n"), [rule])

    def test_round_trip(self):
        for _, rule in self.CASES:
            with self.subTest(rule=rule):
                text = generate.make_text([rule], "module.yaml")
                self.assertEqual(R.normalise(translate.translate(text)), R.normalise([rule]))

    def test_unsupported_forms_stop(self):
        for text in ("X = $(addprefix p_,$(A))", "D += $(dir $(wildcard $(addsuffix x,$(U))))",
                     "X = $(patsubst %.c,%,$(shell ls))"):
            with self.subTest(text=text):
                with self.assertRaises(translate.Unsupported):
                    translate.translate(text + "\n")


class NamesTest(unittest.TestCase):
    """S4: names of the module, build and package data."""

    def test_module_data_names(self):
        self.assertEqual(R.module_yaml_name("sys/Makefile"), "sys/module.yaml")
        self.assertEqual(R.module_yaml_name("makefiles/periph.mk"), "makefiles/periph.module.yaml")
        self.assertEqual(R.make_name("sys/module.yaml"), "sys/Makefile")
        self.assertEqual(R.make_name("pkg/x/x.module.yaml"), "pkg/x/x.mk")
        self.assertTrue(R.is_yaml_name("a/module.yaml"))
        self.assertTrue(R.is_yaml_name("a/b.module.yaml"))
        with self.assertRaises(ValueError):
            R.module_yaml_name("makefiles/auto_init.inc.mk")

    def test_build_and_package_data_names(self):
        self.assertEqual(buildeval.build_yaml_name("cpu/nrf52/Makefile.include"),
                         "cpu/nrf52/build.yaml")
        self.assertEqual(buildeval.build_yaml_name("makefiles/cflags.inc.mk"),
                         "makefiles/cflags.build.yaml")
        self.assertEqual(buildeval.build_yaml_name("makefiles/libc/newlib.mk"),
                         "makefiles/libc/newlib.build.yaml")
        self.assertEqual(buildeval.pkg_yaml_name("pkg/cmsis/Makefile"), "pkg/cmsis/pkg.yaml")
        self.assertEqual(buildeval.pkg_yaml_name("cpu/nrf5x_common/Makefile.nrfx"),
                         "cpu/nrf5x_common/nrfx.pkg.yaml")
        for bad in ("Makefile.dep", "x.c"):
            with self.assertRaises(ValueError):
                buildeval.build_yaml_name(bad)

    def test_build_data_is_not_taken_for_an_adapter_source(self):
        # build.yaml, *.build.yaml and pkg.yaml are read by the build without
        # Make only: config_data must not generate a Make file from them
        for name in ("build.yaml", "makefiles/cflags.build.yaml", "pkg/cmsis/pkg.yaml",
                     "cpu/nrf5x_common/nrfx.pkg.yaml"):
            self.assertFalse(R.is_yaml_name(name), name)


def data_files() -> list:
    listed = subprocess.run(["git", "-C", RIOTBASE, "ls-files", "--cached", "--others",
                             "--exclude-standard"], capture_output=True, text=True,
                            check=True).stdout.split()
    return sorted(p for p in listed if os.path.basename(p) in ("build.yaml", "pkg.yaml")
                  or p.endswith((".build.yaml", ".pkg.yaml")))


class DataFilesTest(unittest.TestCase):
    """D1: every build and package data file of the step is valid schema 3
    and says which Make file it describes."""

    def test_valid(self):
        files = data_files()
        self.assertGreaterEqual(len(files), 30)
        for path in files:
            with self.subTest(path=path):
                with open(os.path.join(RIOTBASE, path), encoding="utf-8") as file:
                    text = file.read()
                self.assertEqual(schema.validate(yaml.safe_load(text)), [])
                self.assertIn("step G3-1", text.split("schema:")[0])

    def test_each_build_data_file_has_its_make_file(self):
        for path in data_files():
            base = os.path.basename(path)
            if base == "build.yaml":
                make = os.path.join(os.path.dirname(path), "Makefile.include")
            elif base == "pkg.yaml":
                make = os.path.join(os.path.dirname(path), "Makefile")
            elif base.endswith(".pkg.yaml"):
                make = os.path.join(os.path.dirname(path), "Makefile." + base[:-9])
            else:
                stem = base[:-len(".build.yaml")]
                make = [os.path.join(os.path.dirname(path), stem + s) for s in (".inc.mk", ".mk")]
                make = next((m for m in make if os.path.exists(os.path.join(RIOTBASE, m))),
                            make[0])
            with self.subTest(path=path):
                self.assertTrue(os.path.exists(os.path.join(RIOTBASE, make)), make)


if __name__ == "__main__":
    unittest.main()
