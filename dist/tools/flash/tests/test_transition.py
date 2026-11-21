#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `flash` moves out of Make.

R1 `just flash <app> <board> [VAR=VALUE…]` runs flash.py (same parameters
   as `just build`); `generate-flash-data` regenerates the adapters
R3 Make keeps its target `flash` (applications and boards outside the data
   still flash with make); its recipe is unchanged
O1 the register lists step g3-02-flash: group 3, target flash, hardware,
   with a board test
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


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def dry_run(self, *args):
        return subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                               "--dry-run", *args], cwd=sample.RIOTBASE, capture_output=True,
                              text=True, check=True).stderr.strip()

    def test_flash_recipe(self):
        self.assertEqual(self.dry_run("flash", "examples/basic/hello-world", "nrf52840dk",
                                      "PROGRAMMER=openocd"),
                         "./dist/tools/flash/flash.py flash -C 'examples/basic/hello-world' "
                         "BOARD='nrf52840dk' PROGRAMMER=openocd")
        self.assertEqual(self.dry_run("generate-flash-data"),
                         "./dist/tools/flash/flash.py generate")

    def test_same_parameters_as_build(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        self.assertEqual(names("flash"), names("build"))
        self.assertTrue(recipes["generate-flash-data"]["private"])


class MakeKeepsFlashTest(unittest.TestCase):
    """R3."""

    def test_flash_target_and_recipe(self):
        with open(os.path.join(sample.RIOTBASE, "Makefile.include"), encoding="utf-8") as file:
            text = file.read()
        self.assertIn("flash: all $(FLASHDEPS)\n\t$(flash-recipe)\n", text)
        self.assertIn("define default-flash-recipe\n  $(call check_cmd,$(FLASHER),Flash program)"
                      "\n  $(PROGRAMMER_FLASH)\nendef", text)


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(sample.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g3-02-flash"]
        self.assertEqual(step["group"], "3")
        self.assertEqual(step["tests"], ["dist/tools/flash/tests"])
        self.assertEqual(step["docs"], "dist/tools/flash/README.md")
        (target,) = step["targets"]
        self.assertEqual((target["name"], target["hardware"]), ("flash", True))
        self.assertTrue(target["now"].startswith("just flash <application> <board>"))
        self.assertIn("nRF52840", target["board_test"])


if __name__ == "__main__":
    unittest.main()
