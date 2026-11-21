#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A5: the algorithm of the build system in pipeline.py, on small
fixtures with positive and negative samples:

  A1 features check (makefiles/features_check.inc.mk)
  A2 fixpoint of the dependency resolution (dependency_resolution.inc.mk:5-40)
  A3 default modules and finalisation (Makefile.include:343-355,
     dependency_resolution.inc.mk:42-95, bindist.inc.mk:2)
  A4 order of the results (sorted, de-duplicated)
  A5 checks of the result and board filtering (Makefile.include:908-993,
     info-global.inc.mk:14-74)

Run: python3 -m unittest discover -s dist/tools/resolver/tests -v
"""

import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
import yaml  # noqa: E402
import pipeline  # noqa: E402
from evaluate import MAKE_ONLY, Evaluator, ResolveError, RIOTBASE  # noqa: E402
from variables import Variables  # noqa: E402


def variables(**words) -> Variables:
    v = Variables()
    for name, value in words.items():
        v.set_words(name, value.split())
    return v


class FeaturesCheckTest(unittest.TestCase):
    """A1."""

    def check(self, **words):
        v = variables(**words)
        pipeline.features_check(v)
        return v

    def test_arch_bug_cpu_features_are_always_required(self):
        v = self.check(FEATURES_PROVIDED="arch_arm bug_x cpu_nrf52 periph_uart")
        self.assertEqual(v.words("FEATURES_USED"), ["arch_arm", "bug_x", "cpu_nrf52"])
        self.assertEqual(v.words("FEATURES_MISSING"), [])

    def test_missing_required_feature(self):
        v = self.check(FEATURES_PROVIDED="periph_uart", FEATURES_REQUIRED="periph_spi periph_uart")
        self.assertEqual(v.words("FEATURES_MISSING"), ["periph_spi"])
        self.assertEqual(v.words("FEATURES_USED"), ["periph_spi", "periph_uart"])

    def test_optional_features_used_only_if_usable(self):
        v = self.check(FEATURES_PROVIDED="a b c", FEATURES_OPTIONAL="a d c",
                       FEATURES_BLACKLIST="c")
        self.assertEqual(v.words("FEATURES_OPTIONAL_USED"), ["a"])
        self.assertEqual(v.words("FEATURES_OPTIONAL_MISSING"), ["c", "d"])
        self.assertEqual(v.words("FEATURES_USED"), ["a"])

    def test_optional_feature_that_would_conflict_is_not_used(self):
        v = self.check(FEATURES_PROVIDED="newlib picolibc", FEATURES_REQUIRED="newlib",
                       FEATURES_OPTIONAL="picolibc", FEATURES_CONFLICT="picolibc:newlib")
        self.assertEqual(v.words("FEATURES_USED"), ["newlib"])
        self.assertEqual(v.words("FEATURES_CONFLICTING"), [])

    def test_required_conflicting_features(self):
        v = self.check(FEATURES_PROVIDED="newlib picolibc", FEATURES_REQUIRED="newlib picolibc",
                       FEATURES_CONFLICT="picolibc:newlib")
        self.assertEqual(v.words("FEATURES_CONFLICTING"), ["newlib", "picolibc"])

    def test_one_out_of_prefers_used_then_usable_then_first(self):
        for words, picked in (
                ({"FEATURES_PROVIDED": "x y", "FEATURES_REQUIRED": "y"}, "y"),   # used
                ({"FEATURES_PROVIDED": "y"}, "y"),                              # usable
                ({"FEATURES_PROVIDED": "y", "FEATURES_BLACKLIST": "y"}, "x"),   # first
                ({"FEATURES_PROVIDED": ""}, "x")):
            with self.subTest(words=words):
                v = self.check(FEATURES_REQUIRED_ANY="x|y", **words)
                self.assertIn(picked, v.words("FEATURES_USED"))
                self.assertEqual(v.words("FEATURES_REQUIRED_ONE_OUT_OF"), [picked])
                missing = [] if picked in words["FEATURES_PROVIDED"].split() else [picked]
                self.assertEqual(v.words("FEATURES_MISSING"), missing)

    def test_blacklisted_used_feature(self):
        v = self.check(FEATURES_PROVIDED="a", FEATURES_REQUIRED="a", FEATURES_BLACKLIST="a")
        self.assertEqual(v.words("FEATURES_USED_BLACKLISTED"), ["a"])

    def test_required_features_follow_later_provided_features(self):
        """The selections added to FEATURES_REQUIRED stay references."""
        v = self.check(FEATURES_PROVIDED="arch_arm")
        v.set_words("FEATURES_PROVIDED", ["arch_arm", "arch_32bit"])
        self.assertEqual(sorted(set(v.words("FEATURES_REQUIRED"))), ["arch_32bit", "arch_arm"])


class Fixture:
    """A temporary repository-like tree for the pipeline: the hooks replace
    Makefile.dep and boards/Makefile.features by fixture rules."""

    def __init__(self, test, deps: list, features_modules: list = None, extra=None):
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        test.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        files = {"makefiles/features_modules.inc.yaml": features_modules or [],
                 "makefiles/defaultmodules_regular.inc.yaml":
                     [{"add": {"DEFAULT_MODULE": ["board", "core"]}}],
                 "makefiles/defaultmodules_no_recursive_deps.inc.yaml":
                     [{"add": {"DEFAULT_MODULE": ["auto_init", "periph_init",
                                                  "periph_init_leds"]}}],
                 "makefiles/defaultmodules_deps.inc.yaml":
                     [{"if": {"has": {"var": "USEMODULE", "match": ["auto_init%"]}},
                       "then": [{"add": {"USEMODULE": ["preprocessor"]}}]}],
                 "makefiles/deprecated_modules.inc.yaml":
                     [{"add": {"DEPRECATED_MODULES": ["old"]}}],
                 "deps.yaml": deps, **(extra or {})}
        for name, rules in files.items():
            path = os.path.join(self.dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as file:
                yaml.safe_dump({"schema": 2, "rules": rules}, file)
        self.v = Variables()
        self.ev = Evaluator(self.v, self.dir)
        self.ev.hooks["Makefile.dep"] = lambda: self.ev.run_file(self.path("deps.yaml"))
        self.ev.hooks["boards/Makefile.features"] = lambda: None
        self.ev.hooks["Makefile.features"] = lambda: None
        self.v.set_words("RIOTBASE", [RIOTBASE])
        self.v.set_words("RIOTBOARD", [os.path.join(RIOTBASE, "boards")])
        self.v.set_words("RIOTPKG", [os.path.join(self.dir, "pkg")])
        self.patch = mock.patch.object(pipeline, "data", self.path)
        self.patch.start()
        test.addCleanup(self.patch.stop)
        self.existing = mock.patch.object(pipeline, "features_existing",
                                          lambda: ["f", "g", "periph_uart"])
        self.existing.start()
        test.addCleanup(self.existing.stop)

    def path(self, name):
        return os.path.join(self.dir, name)


def chain(n: int) -> list:
    """m0 -> m1 -> … -> mn, one rule per link, written in reverse order so
    that each pass adds exactly one module."""
    return [{"if": {"has": {"var": "USEMODULE", "match": [f"m{i}"]}},
             "then": [{"add": {"USEMODULE": [f"m{i + 1}"]}}]} for i in reversed(range(n))]


class FixpointTest(unittest.TestCase):
    """A2."""

    def test_passes_until_nothing_changes(self):
        for n in (0, 1, 3):
            with self.subTest(n=n):
                fx = Fixture(self, chain(n))
                fx.v.set_words("USEMODULE", ["m0"])
                passes = pipeline.resolve_dependencies(fx.ev)
                self.assertEqual(passes, n + 1)
                self.assertEqual([m for m in fx.v.words("USEMODULE") if m.startswith("m")],
                                 [f"m{i}" for i in range(n + 1)])

    def test_feature_used_in_a_later_pass_pulls_its_module(self):
        deps = [{"if": {"has": {"var": "USEMODULE", "match": ["shell"]}},
                 "then": [{"add": {"FEATURES_REQUIRED": ["periph_uart"]}}]}]
        modules = [{"add": {"USEMODULE": [{"select": {"var": "FEATURES_USED",
                                                      "match": ["periph_%"]}}]}}]
        fx = Fixture(self, deps, modules)
        fx.v.set_words("USEMODULE", ["shell"])
        fx.v.set_words("FEATURES_PROVIDED", ["periph_uart"])
        self.assertEqual(pipeline.resolve_dependencies(fx.ev), 2)
        self.assertIn("periph_uart", fx.v.words("USEMODULE"))

    def test_a_change_of_features_used_alone_starts_another_pass(self):
        """dependency_resolution.inc.mk:15,35: FEATURES_USED is part of the state."""
        deps = [{"if": {"has": {"var": "FEATURES_USED", "match": ["f"]}},
                 "then": [{"add": {"USEMODULE": ["needs_f"]}}]}]
        fx = Fixture(self, deps)
        fx.v.set_words("FEATURES_PROVIDED", ["f"])
        fx.v.set_words("FEATURES_REQUIRED", ["f"])
        self.assertEqual(pipeline.resolve_dependencies(fx.ev), 3)
        self.assertIn("needs_f", fx.v.words("USEMODULE"))

    def test_no_fixpoint_is_an_error(self):
        fx = Fixture(self, [{"set": {"var": "COUNTER", "value": "x${COUNTER}",
                                     "flavor": "simple"}},
                            {"add": {"USEPKG": ["${COUNTER}"]}}])
        with mock.patch.object(pipeline, "MAX_PASSES", 5):
            with self.assertRaisesRegex(ResolveError, "no fixpoint"):
                pipeline.resolve_dependencies(fx.ev)

    def test_package_paths_only_for_packages_with_a_build_file(self):
        fx = Fixture(self, [])
        os.makedirs(fx.path("pkg/with"))
        os.makedirs(fx.path("pkg/without"))
        with open(fx.path("pkg/with/Makefile"), "w", encoding="utf-8"):
            pass
        fx.v.set_words("USEPKG", ["without", "with"])
        pipeline.dependency_pass(fx.ev)
        self.assertEqual(fx.v.words("PKG_PATHS"), [fx.path("pkg/with") + "/"])


class DefaultModulesTest(unittest.TestCase):
    """A3."""

    def test_defaults_added_and_disabled(self):
        fx = Fixture(self, [])
        fx.v.set_words("DISABLE_MODULE", ["core", "auto_init"])
        fx.ev.run_file(fx.path("makefiles/defaultmodules_regular.inc.yaml"))
        pipeline.resolve_dependencies(fx.ev)
        modules = fx.v.words("USEMODULE")
        self.assertNotIn("core", modules)
        self.assertNotIn("auto_init", modules)
        self.assertIn("periph_init", modules)
        self.assertIn("periph_init_leds", modules)
        self.assertNotIn("preprocessor", modules)       # needs auto_init%
        self.assertIn("auto_init_%", fx.v.words("DISABLE_MODULE"))

    def test_periph_init_disabled_with_its_submodules(self):
        fx = Fixture(self, [])
        fx.v.set_words("DISABLE_MODULE", ["periph_init"])
        pipeline.resolve_dependencies(fx.ev)
        self.assertNotIn("periph_init_leds", fx.v.words("USEMODULE"))
        self.assertIn("preprocessor", fx.v.words("USEMODULE"))

    def test_deprecated_module_message(self):
        fx = Fixture(self, [])
        fx.v.set_words("USEMODULE", ["old"])
        pipeline.resolve_dependencies(fx.ev)
        self.assertEqual(fx.ev.messages, [("info", "Deprecated modules are in use: old")])

    def test_unknown_feature_is_an_error(self):
        for var in ("FEATURES_PROVIDED", "FEATURES_REQUIRED", "FEATURES_OPTIONAL",
                    "FEATURES_REQUIRED_ANY"):
            with self.subTest(var=var):
                fx = Fixture(self, [])
                fx.v.set_words("FEATURES_PROVIDED", ["f"])
                fx.v.set_words(var, ["f|nonexisting"] if var.endswith("ANY")
                               else ["f", "nonexisting"])
                with self.assertRaisesRegex(ResolveError, "non-existing features.*nonexisting"):
                    pipeline.resolve_dependencies(fx.ev)

    def test_application_order_and_bin_modules(self):
        """bin modules come after the resolution: their dependencies are not
        resolved (makefiles/bindist.inc.mk:2), the application module is left out."""
        fx = Fixture(self, [{"if": {"has": {"var": "USEMODULE", "match": ["abc"]}},
                             "then": [{"add": {"USEMODULE": ["dep_of_abc"]}}]}])
        fx.v.set_words("APPLICATION", ["app"])
        fx.v.set_words("BOARD", ["b"])
        fx.v.add("BIN_USEMODULE", "abc")
        fx.v.add("BIN_USEMODULE", "${APPLICATION_MODULE}")
        pipeline.application(fx.ev)
        modules = fx.v.words("USEMODULE")
        self.assertIn("abc", modules)
        self.assertNotIn("dep_of_abc", modules)
        self.assertNotIn("application_app", modules)
        self.assertEqual(fx.v.get("APPLICATION_MODULE"), "application_app")


class OrderTest(unittest.TestCase):
    """A4: the lists are sorted and without duplicates, like Make's $(sort)."""

    def test_sorted_results(self):
        fx = Fixture(self, [{"add": {"USEMODULE": ["zz", "aa", "zz"]}},
                            {"add": {"USEPKG": ["p2", "p1", "p2"]}}])
        fx.v.set_words("BOARD", ["b"])
        pipeline.application(fx.ev)
        for name in ("USEMODULE", "USEPKG", "FEATURES_USED", "DEFAULT_MODULE"):
            with self.subTest(name=name):
                words = fx.v.words(name)
                self.assertEqual(words, sorted(set(words)))
        self.assertEqual(fx.v.words("USEPKG"), ["p1", "p2"])


class ExpectedErrorsTest(unittest.TestCase):
    """A5."""

    def result(self, **words):
        fx = Fixture(self, [])
        fx.v.set_words("BOARD", ["b"])
        for name, value in words.items():
            fx.v.set_words(name, value.split())
        return fx

    def test_no_problem(self):
        fx = self.result(FEATURES_PROVIDED="f")
        pipeline.expected_errors(fx.ev)
        self.assertEqual(fx.v.get("EXPECT_ERRORS"), "")

    def test_each_problem_is_an_error(self):
        for words, text in (
                ({"FEATURES_MISSING": "g"}, "unsatisfied feature requirements: g"),
                ({"FEATURES_USED_BLACKLISTED": "g"}, "blacklisted: g"),
                ({"FEATURES_CONFLICTING": "f g", "FEATURES_CONFLICT_MSG": "why"},
                 "conflict: f g; Rationale: why"),
                ({"BOARDS_SUPPORTED": "other"}, "not listed in BOARDS_SUPPORTED"),
                ({"BOARD_WHITELIST": "other"}, "not listed in BOARDS_SUPPORTED"),
                ({"BOARDS_UNSUPPORTED": "b"}, "listed in BOARDS_UNSUPPORTED"),
                ({"USEMODULE": "x y", "DISABLE_MODULE": "y"}, "disabled using DISABLE_MODULE: y")):
            with self.subTest(words=words):
                fx = self.result(**words)
                with self.assertRaisesRegex(ResolveError, re.escape(text)):
                    pipeline.expected_errors(fx.ev)

    def test_supported_board_is_no_problem(self):
        fx = self.result(BOARDS_SUPPORTED="other b", BOARDS_UNSUPPORTED="c")
        pipeline.expected_errors(fx.ev)
        self.assertEqual(fx.v.get("EXPECT_ERRORS"), "")

    def test_continue_on_expected_errors(self):
        fx = self.result(FEATURES_MISSING="g", CONTINUE_ON_EXPECTED_ERRORS="1",
                         USEMODULE="x y", DISABLE_MODULE="y")
        pipeline.expected_errors(fx.ev)
        self.assertEqual(fx.ev.messages[-1], ("error", "EXPECT ERRORS!"))
        self.assertEqual(fx.v.words("USEMODULE"), ["x"])

    def test_insecure_modules_only_outside_info_goals(self):
        fx = self.result(USEMODULE="auto_init_telnet")
        with self.assertRaisesRegex(ResolveError, "TELNET_IS_INSECURE"):
            pipeline.insecure_checks(fx.ev)
        fx.v.set_words("I_UNDERSTAND_THAT_TELNET_IS_INSECURE", ["1"])
        pipeline.insecure_checks(fx.ev)
        self.assertEqual(fx.ev.messages[0][0], "warning")


class BoardFilterTest(unittest.TestCase):
    """A5: info-boards-supported."""

    def test_candidates(self):
        for words, result in (({}, ["a", "b", "c"]),
                              ({"BOARDS_SUPPORTED": "a c x"}, ["a", "c"]),
                              ({"BOARDS_UNSUPPORTED": "b"}, ["a", "c"]),
                              ({"BOARDS_SUPPORTED": "a b", "BOARDS_UNSUPPORTED": "a"}, ["b"])):
            with self.subTest(words=words):
                self.assertEqual(pipeline.candidate_boards(variables(**words), ["a", "b", "c"]),
                                 result)

    def test_board_with_missing_feature_is_not_supported(self):
        for provided, result in (("f", True), ("", False)):
            with self.subTest(provided=provided):
                fx = Fixture(self, [])
                fx.v.set_words("FEATURES_PROVIDED", provided.split())
                fx.v.set_words("FEATURES_REQUIRED", ["f"])
                self.assertIs(pipeline.board_supported(fx.ev), result)

    def test_board_with_conflict_after_resolution_is_not_supported(self):
        deps = [{"if": {"has": {"var": "USEMODULE", "match": ["core"]}},
                 "then": [{"add": {"FEATURES_REQUIRED": ["g"]}}]}]
        fx = Fixture(self, deps)
        fx.v.set_words("FEATURES_PROVIDED", ["f", "g"])
        fx.v.set_words("FEATURES_REQUIRED", ["f"])
        fx.v.set_words("FEATURES_CONFLICT", ["f:g"])
        self.assertIs(pipeline.board_supported(fx.ev), False)


class MakeOnlyFilesTest(unittest.TestCase):
    """The files the resolver skips change none of its variables (a test
    may read Make files; the resolver does not)."""

    RESOLVED = re.compile(r"^\s*(USEMODULE|USEPKG|FEATURES_\w+|DISABLE_MODULE|DEFAULT_MODULE|"
                          r"CPU\w*|BOARDS?\w*)\s*[:+?]?=", re.M)

    def test_detector_samples(self):
        self.assertTrue(self.RESOLVED.search("  USEMODULE += x\n"))
        self.assertTrue(self.RESOLVED.search("CPU_MODEL ?= y\n"))
        self.assertFalse(self.RESOLVED.search("CFLAGS += -DUSEMODULE=1\n"))

    def test_make_only_files_assign_no_resolved_variable(self):
        for path in MAKE_ONLY:
            with self.subTest(path=path):
                with open(os.path.join(RIOTBASE, path), encoding="utf-8") as file:
                    self.assertIsNone(self.RESOLVED.search(file.read()))


if __name__ == "__main__":
    unittest.main()
