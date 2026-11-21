# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, R4: the entry point of the build without Make and the transition
rule for Make's `all` (see README: `all` stays in Make for the applications
and boards outside the scope; for the scope the entry point is
`just build`)."""

import json
import os
import shutil
import subprocess
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sample  # noqa: E402

JUST = shutil.which("just")
JUSTFILE = os.path.join(sample.RIOTBASE, "justfile")
TOOL = os.path.join(sample.RIOTBASE, "dist", "tools", "cmake_gen", "cmake_gen.py")


@unittest.skipIf(JUST is None, "just is not installed")
class JustRecipeTest(unittest.TestCase):
    """R1: `just build <app> <board>` runs the generator, never make."""

    def test_dry_run(self):
        res = subprocess.run([JUST, "--justfile", JUSTFILE, "--dry-run", "build",
                              "examples/basic/hello-world", "nrf52840dk", "WERROR=0"],
                             capture_output=True, text=True, check=True)
        self.assertEqual(res.stderr.strip(),
                         "./dist/tools/cmake_gen/cmake_gen.py build -C "
                         "'examples/basic/hello-world' BOARD='nrf52840dk' WERROR=0")

    def test_recipe_parameters(self):
        dump = json.loads(subprocess.run([JUST, "--justfile", JUSTFILE, "--dump",
                                          "--dump-format", "json"], capture_output=True,
                                         text=True, check=True).stdout)
        recipe = dump["recipes"]["build"]
        self.assertEqual([p["name"] for p in recipe["parameters"]], ["app", "board", "vars"])
        self.assertEqual(recipe["dependencies"], [])


class TransitionTest(unittest.TestCase):
    """R3: Make keeps `all` for everything outside the scope; the step is
    registered with its entry point."""

    def test_make_keeps_all(self):
        with open(os.path.join(sample.RIOTBASE, "Makefile.include"), encoding="utf-8") as file:
            text = file.read()
        self.assertIn("\nall: link\n", text)

    def test_registered(self):
        with open(os.path.join(sample.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = yaml.safe_load(file)["steps"]
        step = next(s for s in steps if s["id"] == "g3-01-all")
        self.assertEqual(step["group"], "3")
        self.assertEqual(step["targets"], [{"name": "all", "hardware": False,
                                            "now": "just build <application> <board> "
                                                   "[VAR=VALUE…]"}])

    def test_outside_the_scope_is_refused_with_status_3(self):
        cases = [(["-C", "examples/basic/hello-world", "BOARD=native64", "BINDIR=/x"],
                  "native64"),
                 (["-C", "examples/basic/blinky", "BOARD=nrf52840dk", "BINDIR=/x"],
                  "riot-app.yaml")]
        for args, text in cases:
            with self.subTest(args=args):
                res = subprocess.run([sys.executable, TOOL, "plan", "--no-packages", *args,
                                      "--json", os.devnull], cwd=sample.RIOTBASE,
                                     capture_output=True, text=True, check=False)
                self.assertEqual(res.returncode, 3, res.stderr)
                self.assertIn("error:", res.stderr)

    def test_usage_errors(self):
        res = subprocess.run([sys.executable, TOOL, "plan", "-C", "x"], capture_output=True,
                             text=True, check=False)
        self.assertEqual(res.returncode, 2)
        self.assertIn("BOARD=<board> is required", res.stderr)


if __name__ == "__main__":
    unittest.main()
