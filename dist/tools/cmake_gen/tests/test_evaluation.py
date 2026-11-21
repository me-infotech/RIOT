# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""E1-E4: evaluation of the schema 3 constructs and of the build data
(variables of the resolver, BuildVariables, BuildEvaluator)."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import buildeval  # noqa: E402
from evaluate import Evaluator, OutOfScope, version_at_least  # noqa: E402
import variables as V  # noqa: E402


def touch(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


class FilesTest(unittest.TestCase):
    """E1: `files` and `subdirs` look at the file system like $(wildcard)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        for name in ("b.c", "a.c", "init.c", ".hidden.c", "x.h", "sub/Makefile",
                     "sub2/Makefile", "nomake/x.c"):
            touch(os.path.join(self.dir, name))
        self.v = V.Variables()
        self.v.set("CURDIR", self.dir, "simple")

    def tearDown(self):
        self.tmp.cleanup()

    def test_wildcard_is_sorted_relative_and_skips_hidden_files(self):
        self.assertEqual(self.v.files({"match": ["*.c"]}), ["a.c", "b.c", "init.c"])

    def test_except_patterns(self):
        self.assertEqual(self.v.files({"match": ["*.c"], "except": ["init.c"]}), ["a.c", "b.c"])
        self.v.set("E", "a.%", "simple")
        self.assertEqual(self.v.files({"match": ["*.c"], "except": ["${E}"]}),
                         ["b.c", "init.c"])

    def test_each_pattern_sorted_on_its_own(self):
        self.assertEqual(self.v.files({"match": ["*.h", "*.c"]}), ["x.h", "a.c", "b.c", "init.c"])

    def test_absolute_pattern_and_no_match(self):
        self.assertEqual(self.v.files({"match": [os.path.join(self.dir, "sub")]}),
                         [os.path.join(self.dir, "sub")])
        self.assertEqual(self.v.files({"match": ["*.s"]}), [])

    def test_subdirs_with_the_file(self):
        self.v.set("U", "sub nomake missing sub2", "simple")
        self.assertEqual(self.v.subdirs({"select": {"var": "U"}, "file": "Makefile"}),
                         ["sub/", "sub2/"])
        self.v.set("F", "sub2", "simple")
        self.assertEqual(self.v.subdirs({"select": {"var": "U", "except": ["${F}"]},
                                         "file": "Makefile"}), ["sub/"])

    def test_without_curdir(self):
        with self.assertRaises(ValueError):
            V.Variables().files({"match": ["*.c"]})

    def test_recursive_value_is_evaluated_when_used(self):
        self.v.set("SRC", {"files": {"match": ["*.c"]}})
        touch(os.path.join(self.dir, "c.c"))
        self.assertEqual(self.v.words("SRC"), ["a.c", "b.c", "c.c", "init.c"])


class SelectTest(unittest.TestCase):
    """E2: pattern substitution, macro names, unique, arithmetic."""

    def test_patsubst_keeps_words_that_do_not_match(self):
        self.assertEqual(V.patsubst("%.c", "periph_%", "gpio.c"), "periph_gpio")
        self.assertEqual(V.patsubst("%.c", "periph_%", "README"), "README")
        self.assertEqual(V.patsubst("p_%", "x", "p_a"), "x")
        self.assertEqual(V.patsubst("%", "-I%", "/a"), "-I/a")

    def test_select_order_filter_then_macro_then_pattern(self):
        v = V.Variables()
        v.set("A", "cortex-m4f nrf52 nrf52", "simple")
        self.assertEqual(v.select({"var": "A", "match": ["nrf%"], "macro": True,
                                   "pattern": {"from": "%", "to": "-DCPU_%"}}),
                         ["-DCPU_NRF52", "-DCPU_NRF52"])
        self.assertEqual(v.select({"var": "A", "unique": True}), ["cortex-m4f", "nrf52"])
        self.assertEqual(v.select({"var": "A", "macro": True}),
                         ["CORTEX_M4F", "NRF52", "NRF52"])

    def test_pattern_with_reference(self):
        v = V.Variables()
        v.set("P", "auto_init_", "simple")
        v.set("A", "auto_init_x.c auto_init_y.c", "simple")
        self.assertEqual(v.select({"var": "A", "pattern": {"from": "${P}%.c", "to": "%"}}),
                         ["x", "y"])

    def test_unique_keeps_the_first_occurrence(self):
        self.assertEqual(V.unique(["b", "a", "b", "c", "a"]), ["b", "a", "c"])

    def test_arith(self):
        self.assertEqual(V.arith("0x40000"), 262144)
        self.assertEqual(V.arith("256K"), 262144)
        self.assertEqual(V.arith("0x100000-0"), 1048576)
        self.assertEqual(V.arith("(1+2)*3-4"), 5)
        self.assertEqual(V.arith("-2+3"), 1)
        for bad in ("", "1+", "(1", "1 2", "a"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    V.arith(bad)

    def test_arith_value(self):
        v = V.Variables()
        v.set("RAM_LEN", "0x40000", "simple")
        v.set("X", {"arith": {"expr": "${RAM_LEN}", "format": "hex"}}, "simple")
        v.set("Y", {"arith": {"expr": "${RAM_LEN}-1"}}, "simple")
        self.assertEqual((v.get("X"), v.get("Y")), ("0x40000", "262143"))


class ConditionTest(unittest.TestCase):
    """E3: at_least and nonempty."""

    def ev(self, **values):
        v = V.Variables()
        for name, value in values.items():
            v.set(name, value, "simple")
        return Evaluator(v, "/")

    def test_version_at_least(self):
        for version, minimum, expected in (("13", "8", True), ("8", "8", True), ("7", "8", False),
                                           ("", "8", False), ("15", "15", True),
                                           ("4.2.1", "4.2", True), ("4.1.9", "4.2", False),
                                           ("10", "9", True)):
            with self.subTest(version=version, minimum=minimum):
                self.assertEqual(version_at_least(version, minimum), expected)

    def test_condition_at_least(self):
        cond = {"at_least": {"var": "GCC_VERSION", "version": "8"}}
        self.assertTrue(self.ev(GCC_VERSION="13").condition(cond))
        self.assertFalse(self.ev(GCC_VERSION="").condition(cond))

    def test_condition_nonempty(self):
        cond = {"nonempty": ["A", "B"]}
        self.assertFalse(self.ev().condition(cond))
        self.assertFalse(self.ev(A=" ", B="").condition(cond))
        self.assertTrue(self.ev(B="x").condition(cond))


class BuildEvaluatorTest(unittest.TestCase):
    """E4: providers, the build data of includes, LAST_MAKEFILEDIR."""

    def test_provider_runs_once_and_only_when_read(self):
        calls = []

        def probe(v):
            calls.append(v.get("CC"))
            return "13"
        v = buildeval.BuildVariables({"PROBE_X": probe})
        v.set("CC", "gcc", "simple")
        v.set("GCC_VERSION", "${PROBE_X}")
        self.assertEqual(calls, [])
        self.assertEqual(v.get("GCC_VERSION"), "13")
        self.assertEqual(v.get("PROBE_X"), "13")
        self.assertEqual(calls, ["gcc"])

    def test_data_defines_win_over_providers(self):
        v = buildeval.BuildVariables({"PROBE_X": lambda v: "probe"})
        v.set("PROBE_X", "data", "simple")
        self.assertEqual(v.get("PROBE_X"), "data")

    def test_include_reads_build_data_and_sets_last_makefiledir(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "a", "Makefile.include"), "CFLAGS += -DX\n")
            touch(os.path.join(tmp, "a", "build.yaml"),
                  "schema: 3\nrules:\n  - add: {CFLAGS: [-DA]}\n"
                  "  - include: {path: '${LAST_MAKEFILEDIR}/x.inc.mk'}\n")
            touch(os.path.join(tmp, "a", "x.inc.mk"), "")
            touch(os.path.join(tmp, "a", "x.build.yaml"),
                  "schema: 3\nrules:\n  - set: {var: D, value: '${LAST_MAKEFILEDIR}'}\n")
            v = buildeval.BuildVariables()
            ev = buildeval.BuildEvaluator(v, tmp)
            ev.include_one(os.path.join(tmp, "a", "Makefile.include"), False, "test")
            self.assertEqual(v.get("CFLAGS"), "-DA")
            self.assertEqual(v.get("D"), os.path.join(tmp, "a"))

    def test_make_file_without_data_is_outside_the_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "Makefile.include"), "CFLAGS += -DX\n")
            ev = buildeval.BuildEvaluator(buildeval.BuildVariables(), tmp)
            with self.assertRaises(OutOfScope):
                ev.include_one(os.path.join(tmp, "Makefile.include"), False, "test")
            # a missing optional file is no error (`-include`)
            ev.include_one(os.path.join(tmp, "VERSION"), True, "test")

    def test_module_rules_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "periph.mk"), "")
            touch(os.path.join(tmp, "periph.module.yaml"),
                  "schema: 1\nrules:\n  - set: {var: MODULE, value: periph, flavor: conditional}\n")
            v = buildeval.BuildVariables()
            buildeval.BuildEvaluator(v, tmp).include_one(os.path.join(tmp, "periph.mk"),
                                                         False, "test")
            self.assertEqual(v.get("MODULE"), "periph")


if __name__ == "__main__":
    unittest.main()
