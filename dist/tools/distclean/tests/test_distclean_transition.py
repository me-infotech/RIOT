#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, R4, O1: how the application's `distclean` moves out of Make.

R1 `just distclean <app> <board> [VAR=VALUE…]` runs clean.py distclean
   (the same parameters as `just build` and `just clean`, public)
R3 Make keeps its target `distclean` (applications and boards outside the
   data): the recipes of Makefile.include and pkg/pkg.mk are the ones of
   the base commit, line for line; `make -n distclean` works for a board
   outside the data where clean.py stops with exit status 3
R4 the root `make distclean` stays in Make and unchanged: its rules are
   those of the bases, `make -n distclean` (sub-makes replaced by `echo`)
   prints exactly what the Makefile of both base commits prints, iterating
   every application and tool directory (the scope applications included,
   with Make's application-level distclean of the default board)
O1 the register lists step g2c-02-distclean: group 2C, target distclean,
   no hardware
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402
import sample as S  # noqa: E402

JUST = shutil.which("just")
GIT = shutil.which("git")
MAKE = shutil.which("make")
# the base of the application-level target (Make only) and of the root
# Makefile after step G2C-3 (its `distclean` runs `_pkg-clean` through just)
BASES = ("74a0fb9743", "9cd0952bc7")
RECIPE = ("distclean:\n"
          "\t-@$(foreach dir,$(PKG_PATHS),\"$(MAKE)\" -C $(dir) distclean $(NEWLINE))\n"
          "\t-@rm -rf $(BINDIRBASE)\n")
PKG_RECIPE = ("ifeq ($(PKG_SOURCE_DIR),$(PKG_BUILD_DIR))\n"
              "# This is the case for packages that are built within their source directory\n"
              "# e.g. micropython and openthread\n"
              "clean::\n"
              "\t@-test -d $(PKG_SOURCE_DIR) && $(GIT_IN_PKG) clean -xdff '**' -e "
              "$(PKG_STATE:$(PKG_SOURCE_DIR)/%='%*')\n"
              "else\n"
              "clean::\n"
              "\trm -rf $(PKG_BUILD_DIR)\n"
              "endif\n"
              "\n"
              "distclean:: clean\n"
              "\trm -rf $(PKG_SOURCE_DIR)\n")
ROOT_RULES = ("distclean: docclean _pkg-clean $(CLEAN_DIRS:%=DISTCLEAN--%)\n"
              "\t@echo \"Cleaned everything.\"\n",
              "$(CLEAN_DIRS:%=DISTCLEAN--%):\n"
              "\t-\"$(MAKE)\" -C $(@:DISTCLEAN--%=%) distclean\n")
OWNERS = {"Makefile.include": (RECIPE,), "pkg/pkg.mk": (PKG_RECIPE,)}


def show(commit: str, path: str) -> str:
    res = subprocess.run([GIT, "-C", D.RIOTBASE, "show", f"{commit}:{path}"],
                         capture_output=True, text=True, check=False)
    return res.stdout if res.returncode == 0 else None


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def test_distclean_recipe(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(D.RIOTBASE, "justfile"),
                              "--dry-run", "distclean", D.APPS["hello-world"], D.BOARD, "-B",
                              "/tmp/b"], cwd=D.RIOTBASE, capture_output=True, text=True,
                             check=True)
        self.assertEqual(res.stderr.strip(),
                         "./dist/tools/clean/clean.py distclean -C 'examples/basic/hello-world' "
                         "BOARD='nrf52840dk' -B /tmp/b")

    def test_same_parameters_as_build_and_clean(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(D.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        self.assertEqual(names("distclean"), names("build"))
        self.assertEqual(names("distclean"), names("clean"))
        self.assertFalse(recipes["distclean"]["private"])


class MakeKeepsDistcleanTest(unittest.TestCase):
    """R3."""

    def test_recipes(self):
        for owner, recipes in dict(OWNERS, Makefile=ROOT_RULES).items():
            with open(os.path.join(D.RIOTBASE, owner), encoding="utf-8") as file:
                text = file.read()
            for recipe in recipes:
                with self.subTest(owner=owner, recipe=recipe[:20]):
                    self.assertIn(recipe, text)

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_recipes_as_in_the_base_commits(self):
        rules = dict(OWNERS, Makefile=ROOT_RULES[1:])
        for base in BASES:
            for owner, recipes in rules.items():
                text = show(base, owner)
                if text is None:
                    self.skipTest(f"base commit {base} not in this checkout")
                for recipe in recipes:
                    with self.subTest(base=base, owner=owner):
                        self.assertIn(recipe, text)
        # the root rule itself is that of step G2C-3
        self.assertIn(ROOT_RULES[0], show(BASES[1], "Makefile"))

    @unittest.skipIf(MAKE is None, "make is not installed")
    def test_make_distcleans_outside_the_data(self):
        with tempfile.TemporaryDirectory(prefix="g2c2-r3-") as tmp:
            app = S.copy_app(D.RIOTBASE, tmp, "hello-world")
            for board in (["BOARD=native64"], []):    # [] the default board (root distclean)
                argv = [*board, f"RIOTBASE={D.RIOTBASE}"]
                status, text = S.run(["make", "--no-print-directory", "-C", app, *argv, "-n",
                                      "distclean"])
                with self.subTest(board=board):
                    self.assertEqual(status, 0, text)
                    self.assertIn(f"rm -rf {app}/bin", text.split("\n"))
            status, text = S.run([sys.executable, D.CLI, "distclean", "-n", "-C", app,
                                  "BOARD=native64", f"RIOTBASE={D.RIOTBASE}"])
            self.assertEqual(status, 3, text)
            self.assertIn("native64", text)
            self.assertTrue(os.path.isfile(os.path.join(app, "Makefile")))


@unittest.skipIf(MAKE is None or GIT is None or JUST is None, "make, git or just missing")
class RootDistcleanTest(unittest.TestCase):
    """R4."""

    @staticmethod
    def dry_run(makefile: str) -> tuple:
        # with -n Make runs the lines with $(MAKE): `echo` prints them instead
        return S.run(["make", "--no-print-directory", "-n", "-f", makefile, "distclean",
                      "MAKE=echo"], cwd=D.RIOTBASE)

    def test_root_distclean_as_in_the_bases(self):
        status, now = self.dry_run(os.path.join(D.RIOTBASE, "Makefile"))
        self.assertEqual(status, 0, now)
        lines = now.split("\n")
        dirs = [line.split()[2] for line in lines if re.fullmatch(r'"echo" -C \S+ distclean',
                                                                  line)]
        self.assertGreater(len(dirs), 500)
        for app in D.APPS.values():
            self.assertIn(app, dirs)
        self.assertEqual(lines[-1], 'echo "Cleaned everything."')
        for base in BASES:
            text = show(base, "Makefile")
            if text is None:
                self.skipTest(f"base commit {base} not in this checkout")
            with self.subTest(base=base), tempfile.TemporaryDirectory(prefix="g2c2-r4-") as tmp:
                with open(os.path.join(tmp, "Makefile"), "w", encoding="utf-8") as file:
                    file.write(text)
                # the justfile next to the Makefile (step G2C-3's `_pkg-clean`)
                os.symlink(os.path.join(D.RIOTBASE, "justfile"), os.path.join(tmp, "justfile"))
                self.assertEqual(self.dry_run(os.path.join(tmp, "Makefile")), (status, now))


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(D.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g2c-02-distclean"]
        self.assertEqual(step["group"], "2C")
        self.assertEqual(step["tests"], ["dist/tools/distclean/tests"])
        self.assertEqual(step["docs"], "dist/tools/clean/README.md")
        (target,) = step["targets"]
        self.assertEqual((target["name"], target["hardware"]), ("distclean", False))
        self.assertNotIn("board_test", target)
        self.assertTrue(target["now"].startswith("just distclean <application> <board>"))


if __name__ == "__main__":
    unittest.main()
