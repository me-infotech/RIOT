#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `clean` moves out of Make.

R1 `just clean <app> <board> [VAR=VALUE…]` runs clean.py (same parameters as
   `just build`); `generate-clean-data` (private) regenerates the adapters
R3 Make keeps its target `clean` (applications and boards outside the data
   still clean with make): the recipes of Makefile.include and pkg/pkg.mk
   are the ones of the base commit, line for line, and `make clean` works
   for a board outside the data where clean.py stops with exit status 3
O1 the register lists step g2c-01-clean: group 2C, target clean, no
   hardware
"""

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
import sample  # noqa: E402

JUST = shutil.which("just")
GIT = shutil.which("git")
MAKE = shutil.which("make")
BASE = "74a0fb9743"
RECIPE = ("clean:\n"
          "ifndef MAKE_RESTARTS\n"
          "\t-@$(foreach dir,$(PKG_PATHS),\"$(MAKE)\" -C $(dir) clean $(NEWLINE))\n"
          "\t-@rm -rf $(BINDIR)\n"
          "\t-@rm -rf $(SCANBUILD_OUTPUTDIR)\n"
          "endif\n")
PKG_RECIPE = ("ifeq ($(PKG_SOURCE_DIR),$(PKG_BUILD_DIR))\n"
              "# This is the case for packages that are built within their source directory\n"
              "# e.g. micropython and openthread\n"
              "clean::\n"
              "\t@-test -d $(PKG_SOURCE_DIR) && $(GIT_IN_PKG) clean -xdff '**' -e "
              "$(PKG_STATE:$(PKG_SOURCE_DIR)/%='%*')\n"
              "else\n"
              "clean::\n"
              "\trm -rf $(PKG_BUILD_DIR)\n"
              "endif\n")
OWNERS = {"Makefile.include": RECIPE, "pkg/pkg.mk": PKG_RECIPE}


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def dry_run(self, *args):
        return subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                               "--dry-run", *args], cwd=sample.RIOTBASE, capture_output=True,
                              text=True, check=True).stderr.strip()

    def test_clean_recipe(self):
        self.assertEqual(self.dry_run("clean", sample.APPS["hello-world"], sample.BOARD,
                                      "-B", "/tmp/b"),
                         "./dist/tools/clean/clean.py clean -C 'examples/basic/hello-world' "
                         "BOARD='nrf52840dk' -B /tmp/b")
        self.assertEqual(self.dry_run("generate-clean-data"),
                         "./dist/tools/clean/clean.py generate")

    def test_same_parameters_as_build(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        self.assertEqual(names("clean"), names("build"))
        self.assertFalse(recipes["clean"]["private"])
        self.assertTrue(recipes["generate-clean-data"]["private"])


class MakeKeepsCleanTest(unittest.TestCase):
    """R3."""

    def test_recipes(self):
        for owner, recipe in OWNERS.items():
            with self.subTest(owner=owner):
                with open(os.path.join(sample.RIOTBASE, owner), encoding="utf-8") as file:
                    self.assertIn(recipe, file.read())

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_recipes_as_in_the_base_commit(self):
        for owner, recipe in OWNERS.items():
            res = subprocess.run([GIT, "-C", sample.RIOTBASE, "show", f"{BASE}:{owner}"],
                                 capture_output=True, text=True, check=False)
            if res.returncode != 0:
                self.skipTest(f"base commit {BASE} not in this checkout")
            with self.subTest(owner=owner):
                self.assertIn(recipe, res.stdout)

    @unittest.skipIf(MAKE is None, "make is not installed")
    def test_make_cleans_outside_the_data(self):
        with tempfile.TemporaryDirectory(prefix="g2c-r3-") as tmp:
            app = sample.copy_app(sample.RIOTBASE, tmp, "hello-world")
            board = ["BOARD=native64", f"RIOTBASE={sample.RIOTBASE}"]
            status, text = sample.run(["make", "--no-print-directory", "-C", app, *board,
                                       "-n", "clean"])
            self.assertEqual(status, 0, text)
            self.assertIn(f"rm -rf {app}/bin/native64", text)
            status, text = sample.run([sys.executable, sample.CLI, "clean", "-n", "-C", app,
                                       *board])
            self.assertEqual(status, 3, text)
            self.assertIn("native64", text)


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(sample.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g2c-01-clean"]
        self.assertEqual(step["group"], "2C")
        self.assertEqual(step["tests"], ["dist/tools/clean/tests"])
        self.assertEqual(step["docs"], "dist/tools/clean/README.md")
        (target,) = step["targets"]
        self.assertEqual((target["name"], target["hardware"]), ("clean", False))
        self.assertNotIn("board_test", target)
        self.assertTrue(target["now"].startswith("just clean <application> <board>"))


if __name__ == "__main__":
    unittest.main()
