#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""D1-D4: the test data are the single source of the test variables
(the generic checks of the terminal data, dist/tools/term/tests/test_data.py,
cover them too: valid, adapters up to date, owners include their adapter).

D1 tests.test.yaml holds the variables of tests.inc.mk (the export of
   TESTRUNNER_RESET_AFTER_TERM for test, test-as-root, test-with-config;
   TESTS ?= PROBE_TESTS; TEST_DEPS += TERMDEPS; TEST_EXECUTOR(_FLAGS) ?=);
   tests.inc.mk no longer assigns them and keeps its rules (R3)
D2 test.yaml (Makefile.include: RIOTPROJECT ?= PROBE_RIOTPROJECT,
   DLCACHE_DIR ?= RIOTBASE/.dlcache) and setup_dirs.test.yaml (PYTHONPATH :=,
   at the end of setup_dirs.inc.mk); Makefile.include no longer assigns them
D3 the probes PROBE_TESTS and PROBE_RIOTPROJECT keep the text of Make's
   former lines and are defined before the directories need them
D4 the adapters are what `term.py generate` writes from the data
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import tsample as S  # noqa: E402

sys.path.insert(0, os.path.join(S.TOOL, "..", "term"))
import termdata as T  # noqa: E402


def read(rel_path: str) -> str:
    with open(os.path.join(S.RIOTBASE, rel_path), encoding="utf-8") as file:
        return file.read()


def assigned(text: str, name: str) -> list:
    return re.findall(rf"^\s*(?:export\s+)?{name}\s*[:+?]?=.*$", text, re.M)


class TestsDataTest(unittest.TestCase):
    """D1."""

    def test_rules(self):
        rules = T.load(os.path.join(S.RIOTBASE, "makefiles/tests/tests.test.yaml"))
        body = [{k: v for k, v in r.items() if k != "comment"} for r in rules]
        self.assertEqual(body, [
            {"export": {"targets": "test test-as-root test-with-config",
                        "vars": ["TESTRUNNER_RESET_AFTER_TERM"]}},
            {"set": {"var": "TESTS", "value": "${PROBE_TESTS}", "flavor": "conditional"}},
            {"add": {"TEST_DEPS": ["${TERMDEPS}"]}},
            {"set": {"var": "TEST_EXECUTOR", "value": "", "flavor": "conditional"}},
            {"set": {"var": "TEST_EXECUTOR_FLAGS", "value": "", "flavor": "conditional"}}])

    def test_make_file(self):
        text = read("makefiles/tests/tests.inc.mk")
        self.assertIn("include $(RIOTMAKE)/tests/tests.test.inc.mk\n", text)
        for name in ("TESTS", "TEST_DEPS", "TEST_EXECUTOR", "TEST_EXECUTOR_FLAGS"):
            with self.subTest(name=name):
                self.assertEqual(assigned(text, name), [])
        self.assertNotIn("TESTRUNNER_RESET_AFTER_TERM", text.split("include $(RIOTMAKE)")[1])
        self.assertIn("test: $(TEST_DEPS)\n\t$(Q) for t in $(TESTS); do \\\n"
                      "\t\t$(TEST_EXECUTOR) $(TEST_EXECUTOR_FLAGS) $$t || exit 1; \\\n"
                      "\tdone\n", text)
        self.assertIn("test/available:\n", text)
        self.assertIn("test-as-root: $(TEST_DEPS)\n", text)        # T4
        self.assertIn("test-with-config: test-with-config/check-config", text)


class DirectoryDataTest(unittest.TestCase):
    """D2."""

    def test_rules(self):
        root = T.load(os.path.join(S.RIOTBASE, "test.yaml"))
        self.assertEqual([r["set"] for r in root], [
            {"var": "RIOTPROJECT", "value": "${PROBE_RIOTPROJECT}", "flavor": "conditional"},
            {"var": "DLCACHE_DIR", "value": "${RIOTBASE}/.dlcache", "flavor": "conditional"}])
        dirs = T.load(os.path.join(S.RIOTBASE, "makefiles/setup_dirs.test.yaml"))
        self.assertEqual([r["set"] for r in dirs], [
            {"var": "PYTHONPATH", "value": "${RIOTBASE}/dist/pythonlibs/:${PYTHONPATH}",
             "flavor": "simple"}])

    def test_make_files(self):
        text = read("Makefile.include")
        for name in ("RIOTPROJECT", "DLCACHE_DIR", "PYTHONPATH"):
            with self.subTest(name=name):
                self.assertEqual(assigned(text, name), [])
        order = [text.index(s) for s in ("DLCACHE                         ?=",
                                         "include $(RIOTMAKE)/term_providers.inc.mk\n",
                                         "include $(RIOTBASE)/test.inc.mk\n",
                                         "MAKEOVERRIDES +=",
                                         "include $(abspath $(RIOTMAKE)/setup_dirs.inc.mk)")]
        self.assertEqual(order, sorted(order))
        setup = read("makefiles/setup_dirs.inc.mk")
        self.assertTrue(setup.rstrip().endswith("include $(RIOTMAKE)/setup_dirs.test.inc.mk"))
        self.assertLess(setup.index("override DLCACHE_DIR"),
                        setup.index("include $(RIOTMAKE)/setup_dirs.test.inc.mk"))


class ProbeTextTest(unittest.TestCase):
    """D3."""

    def test_probes(self):
        text = read("makefiles/term_providers.inc.mk")
        self.assertIn("PROBE_TESTS = $(foreach file,$(wildcard $(APPDIR)/tests/*[^~]),\\\n"
                      "                        $(shell test -f $(file) -a -x $(file) && "
                      "echo $(file)))\n", text)
        self.assertIn("PROBE_RIOTPROJECT = $(shell git rev-parse --show-toplevel 2>/dev/null"
                      " || pwd)\n", text)
        for line in text.split("\n"):
            if line.startswith("PROBE_"):
                self.assertRegex(line, r"^PROBE_[A-Z_]+ = ")   # recursive only


class AdapterTest(unittest.TestCase):
    """D4."""

    def test_generated(self):
        for data in ("makefiles/tests/tests.test.yaml", "test.yaml",
                     "makefiles/setup_dirs.test.yaml"):
            path = os.path.join(S.RIOTBASE, data)
            with self.subTest(data=data):
                self.assertIn(path, T.all_data())
                self.assertEqual(read(os.path.relpath(T.adapter_name(path), S.RIOTBASE)),
                                 T.expected_adapter(path))


if __name__ == "__main__":
    unittest.main()
