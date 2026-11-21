#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C4: Make file -> rules -> YAML -> rules -> Make file keeps the rules.

For every converted file, the rules of the original Make file (from the
base commit in scope.yaml), of the generated Make file and of the YAML are
equal in normal form. Needs git and the base commit; skipped without them
(e.g. in a shallow CI clone, where the parity tests still run).

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import os
import shutil
import subprocess
import sys
import unittest

import yaml

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOL)

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import rules as R  # noqa: E402
from generate import make_text  # noqa: E402
from translate import translate  # noqa: E402

SAMPLE = """\
# header

ifneq (,$(filter-out netdev_default, $(filter netdev_%,$(USEMODULE))))
  USEMODULE += netdev
  USEMODULE += netdev_register   # comment
endif
ifeq (periph_rtt,$(filter periph_rtc periph_rtt,$(USEMODULE)))
  USEMODULE += rtt_rtc
endif
ifneq (,$(filter $(CPU_CORE),cortex-m4f cortex-m7))
  FEATURES_PROVIDED += cortexm_fpu
endif
ifeq ($(CPU_CORE),cortex-m0)
  CPU_ARCH := armv6m
else
  ifeq ($(CPU_CORE),cortex-m3)
    CPU_ARCH := armv7m
  else
    $(error Unknown core: $(CPU_CORE))
  endif
endif
ifeq ($(OS) $(OS_ARCH),Linux x86_64)
  FEATURES_PROVIDED += rust_target
endif
-include $(sort $(USEMODULE:%=$(RIOTBASE)/sys/%/Makefile.dep))
FEATURES_CONFLICT_MSG += "Only one standard C library can be used."
DISABLE_LIBSTDCPP ?= 1
"""


def base_available(rev: str) -> bool:
    if shutil.which("git") is None:
        return False
    return subprocess.run(["git", "-C", R.RIOTBASE, "cat-file", "-e", f"{rev}^{{commit}}"],
                          capture_output=True, check=False).returncode == 0


class RoundTripTest(unittest.TestCase):

    def test_sample_keeps_its_rules(self):
        rules = translate(SAMPLE)
        document = yaml.safe_load(R.dump_yaml(rules, "t"))
        self.assertEqual(document["rules"], rules)
        generated = make_text(document["rules"], "deps.yaml")
        self.assertEqual(config_data.roundtrip_problems(SAMPLE, generated, rules), [])

    def test_generated_text_is_a_fixpoint(self):
        """Translating the generated file gives the YAML rules again, exactly
        (after the header comment): nothing drifts on repeated conversion."""
        rules = translate(SAMPLE)
        self.assertEqual(translate(make_text(rules, "deps.yaml"))[1:], rules)

    def test_a_changed_rule_is_found(self):
        rules = translate(SAMPLE)
        rules[1]["then"][0]["add"]["USEMODULE"] = ["netdev_x"]
        problems = config_data.roundtrip_problems(SAMPLE, make_text(rules, "d.yaml"), rules)
        self.assertEqual(len(problems), 2, problems)

    def test_a_changed_else_or_elif_branch_is_found(self):
        def changed(edit):
            rules = translate(SAMPLE)
            core = next(r for r in rules if r.get("if") == {"equals": {"CPU_CORE": "cortex-m0"}})
            edit(core)
            return config_data.roundtrip_problems(SAMPLE, make_text(rules, "d.yaml"), rules)

        def deepest_else(core):
            core["else"][0]["else"][0]["error"] = "other"

        def as_elif(core):
            inner = core.pop("else")[0]
            inner["then"] = [{"set": {"var": "CPU_ARCH", "value": "x", "flavor": "simple"}}]
            core["elif"] = [{"if": inner["if"], "then": inner["then"]}]
            core["else"] = inner["else"]

        for edit in (deepest_else, as_elif):
            with self.subTest(edit=edit.__name__):
                self.assertEqual(len(changed(edit)), 2)

    def test_normal_form(self):
        self.assertEqual(R.normalise([{"add": {"V": ["a"]}}, {"comment": "x"},
                                      {"comment": "y", "add": {"V": ["b"]}}]),
                         [{"add": {"V": ["a", "b"]}}])
        nested = [{"if": {"equals": {"C": "1"}}, "then": [],
                   "else": [{"if": {"equals": {"C": "2"}}, "then": [], "else": []}]}]
        chained = [{"if": {"equals": {"C": "1"}}, "then": [],
                    "elif": [{"if": {"equals": {"C": "2"}}, "then": []}]}]
        self.assertEqual(R.normalise(nested), R.normalise(chained))
        nested[0]["else"][0]["else"] = [{"info": "x"}]
        self.assertNotEqual(R.normalise(nested), R.normalise(chained))
        self.assertEqual(R.normalise([{"set": {"var": "A", "value": "1"}}]),
                         R.normalise([{"set": {"var": "A", "value": "1",
                                               "flavor": "recursive"}}]))
        self.assertNotEqual(R.normalise([{"set": {"var": "A", "value": "1"}}]),
                            R.normalise([{"set": {"var": "A", "value": "1",
                                                  "flavor": "simple"}}]))


class RepositoryRoundTripTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scope = config_data.load_scope()
        if not base_available(cls.scope["base"]):
            raise unittest.SkipTest(f"base commit {cls.scope['base'][:10]} not available")

    def test_original_generated_and_yaml_rules_are_equal(self):
        for path in config_data.converted_files(self.scope):
            with self.subTest(path=path):
                self.assertEqual(config_data.file_roundtrip_problems(path, self.scope,
                                                                     self.scope["base"]), [])

    def test_roundtrip_command(self):
        result = subprocess.run([sys.executable, os.path.join(TOOL, "config_data.py"),
                                 "roundtrip"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        n = len(config_data.converted_files(self.scope))
        self.assertIn(f"{n}/{n} files: original = generated = YAML", result.stdout)


if __name__ == "__main__":
    unittest.main()
