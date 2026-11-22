#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `test` and `test/available` move out of Make.

R1 `just test|test-available <app> <board> [VAR=VALUE…]` run test.py with
   each argument as one word (TESTS may name several scripts); same
   parameters as `just flash`
R3 Make keeps test, test/available (applications outside the data),
   test-as-root and test-with-config (T4); live Make, which now reads the
   generated adapters (tests.test.inc.mk, test.inc.mk,
   setup_dirs.test.inc.mk) and the probes, gives the golden output of the
   base for every case (`make -n` and the run, with the script environment)
O1 the register lists step g2b-03-test: group 2B, both targets, hardware,
   with a board test
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import tsample as S  # noqa: E402
import test_parity as TP  # noqa: E402

JUST = shutil.which("just")
MAKE = shutil.which("make")


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def dump(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True,
                             text=True, check=True)
        return json.loads(res.stdout)["recipes"]

    def test_recipes(self):
        recipes = self.dump()
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        for recipe, goal in (("test", "test"), ("test-available", "test/available")):
            with self.subTest(recipe=recipe):
                self.assertEqual(names(recipe), names("flash"))
                self.assertFalse(recipes[recipe]["private"])
                self.assertIn("positional-arguments", json.dumps(recipes[recipe]["attributes"]))
                res = subprocess.run([JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"),
                                      "--dry-run", recipe, "a", "b", "TESTS=x y", "Q=1"],
                                     cwd=S.RIOTBASE, capture_output=True, text=True, check=True)
                self.assertEqual(res.stderr.strip(),
                                 'app="$1" board="$2"; shift 2; exec ./dist/tools/test/test.py '
                                 f'{goal} -C "$app" BOARD="$board" "$@"')

    def test_one_word_per_argument(self):
        with tempfile.TemporaryDirectory(prefix="g2b-test-") as tmp:
            run = S.Run(S.RIOTBASE, S.APPS["hello-world"], S.case(), tmp)
            res = subprocess.run([JUST, "test", S.APPS["hello-world"], S.BOARD,
                                  f"TESTS={run.rec} {run.rec}", "X=a b"], cwd=S.RIOTBASE,
                                 env=run.env(), capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)
            with open(run.log, encoding="utf-8") as file:
                lines = file.read().split("\n")
        self.assertEqual(len([l for l in lines if l.startswith("script ")]), 2)
        flags = [l for l in lines if l.startswith("  MAKEFLAGS=")][0]
        self.assertIn(" -- X=a\\ b TESTS=", flags)


class MakeKeepsRulesTest(unittest.TestCase):
    """R3: the rules."""

    def test_rules(self):
        with open(os.path.join(S.RIOTBASE, "makefiles", "tests", "tests.inc.mk"),
                  encoding="utf-8") as file:
            text = file.read()
        for rule in ("test: ..in-docker-container\n", "test: $(TEST_DEPS)\n",
                     "test/available:\n", "test-as-root: $(TEST_DEPS)\n",
                     "test-with-config: test-with-config/check-config $(TEST_DEPS)\n"):
            with self.subTest(rule=rule):
                self.assertIn(rule, text)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """R3: live Make with the adapters = golden."""

    def test_hello_world(self):
        TP.check_app(self, "hello-world", make=True)

    def test_gnrc_networking(self):
        TP.check_app(self, "gnrc_networking", make=True)

    def test_bindist(self):
        TP.check_app(self, "bindist", make=True)


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(S.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g2b-03-test"]
        self.assertEqual(step["group"], "2B")
        self.assertEqual(step["tests"], ["dist/tools/test/tests"])
        self.assertEqual(step["docs"], "dist/tools/test/README.md")
        targets = {t["name"]: t for t in step["targets"]}
        self.assertEqual(sorted(targets), ["test", "test/available"])
        for name, recipe in (("test", "test"), ("test/available", "test-available")):
            with self.subTest(target=name):
                self.assertTrue(targets[name]["hardware"])
                self.assertTrue(targets[name]["now"].startswith(
                    f"just {recipe} <application> <board>"))
                self.assertIn("make", targets[name]["board_test"])


if __name__ == "__main__":
    unittest.main()
