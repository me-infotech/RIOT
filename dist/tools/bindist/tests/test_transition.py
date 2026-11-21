#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `bindist` moves out of Make.

R1 `just bindist <app> <board> [VAR=VALUE…]` runs bindist.py (same
   parameters as `just build`); `generate-dist-data` (private) regenerates
   the adapters
R3 Make keeps its target `bindist` (applications and boards outside the data
   still make their distribution with make); its recipe is the one of the
   base commit, line for line
O1 the register lists step g3-03-bindist: group 3, target bindist, no
   hardware
"""

import os
import shutil
import subprocess
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402

JUST = shutil.which("just")
GIT = shutil.which("git")
BASE = "8324f6c5e9"
RECIPE = ("bindist: all\n"
          "\t@mkdir -p bindist\n"
          "\t@for i in $(DIST_FILES) ; do \\\n"
          "\t\techo Copying $$i to bindist. ; \\\n"
          "\t\tcp -a --parents $$i bindist ; \\\n"
          "\t\tdone\n"
          "\t@cp -a bin/$(BOARD)/$(APPLICATION).bin bindist\n"
          "\n"
          "\t@echo \"BINDIST_RIOT_VERSION=$(RIOT_VERSION)\" > bindist/Makefile.distcheck\n"
          "\t@echo \"BINDIST_GIT_HEAD=$$(git -C $(RIOTBASE) describe)\" >> "
          "bindist/Makefile.distcheck\n")
OWNER = os.path.join(sample.RIOTBASE, "makefiles", "bindist.inc.mk")


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def dry_run(self, *args):
        return subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                               "--dry-run", *args], cwd=sample.RIOTBASE, capture_output=True,
                              text=True, check=True).stderr.strip()

    def test_bindist_recipe(self):
        self.assertEqual(self.dry_run("bindist", sample.APP_DIR, sample.BOARD, "-B", "/tmp/b"),
                         "./dist/tools/bindist/bindist.py bindist -C 'examples/advanced/bindist' "
                         "BOARD='nrf52840dk' -B /tmp/b")
        self.assertEqual(self.dry_run("generate-dist-data"),
                         "./dist/tools/bindist/bindist.py generate")

    def test_same_parameters_as_build(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        self.assertEqual(names("bindist"), names("build"))
        self.assertFalse(recipes["bindist"]["private"])
        self.assertTrue(recipes["generate-dist-data"]["private"])


class MakeKeepsBindistTest(unittest.TestCase):
    """R3."""

    def test_bindist_target_and_recipe(self):
        with open(OWNER, encoding="utf-8") as file:
            text = file.read()
        self.assertIn(RECIPE, text)
        self.assertIn("prepare_check_bindist:", text)
        self.assertIn("check_bindist: prepare_check_bindist all", text)

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_recipe_as_in_the_base_commit(self):
        res = subprocess.run([GIT, "-C", sample.RIOTBASE, "show",
                              f"{BASE}:makefiles/bindist.inc.mk"], capture_output=True,
                             text=True, check=False)
        if res.returncode != 0:
            self.skipTest(f"base commit {BASE} not in this checkout")
        self.assertIn(RECIPE, res.stdout)
        with open(OWNER, encoding="utf-8") as file:
            now = file.read()
        tail = lambda t: t[t.index("bindist: all"):]  # noqa: E731
        self.assertEqual(tail(now), tail(res.stdout))


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(sample.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g3-03-bindist"]
        self.assertEqual(step["group"], "3")
        self.assertEqual(step["tests"], ["dist/tools/bindist/tests"])
        self.assertEqual(step["docs"], "dist/tools/bindist/README.md")
        (target,) = step["targets"]
        self.assertEqual((target["name"], target["hardware"]), ("bindist", False))
        self.assertNotIn("board_test", target)
        self.assertTrue(target["now"].startswith("just bindist <application> <board>"))


if __name__ == "__main__":
    unittest.main()
