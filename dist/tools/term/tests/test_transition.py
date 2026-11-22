#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `term` and `cleanterm` move out of Make.

R1 `just term|cleanterm <app> <board> [VAR=VALUE…]` run term.py (same
   parameters as `just flash`); `generate-term-data` (private) regenerates
   the adapters
R3 Make keeps its targets `term` and `cleanterm` (applications and boards
   outside the data); their recipes are unchanged, and live Make, which now
   reads the generated adapters and probes, gives the golden output of the
   base commit for every case (`make -n` and, for the terminals on PATH and
   the image, the terminal call)
O1 the register lists step g2b-01-term: group 2B, targets term and
   cleanterm, hardware, with a board test
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
import harness  # noqa: E402
import sample  # noqa: E402

JUST = shutil.which("just")
MAKE = shutil.which("make")


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def dry_run(self, *args):
        return subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                               "--dry-run", *args], cwd=sample.RIOTBASE, capture_output=True,
                              text=True, check=True).stderr.strip()

    def test_recipes(self):
        for recipe in ("term", "cleanterm"):
            with self.subTest(recipe=recipe):
                self.assertEqual(self.dry_run(recipe, "examples/basic/hello-world", "nrf52840dk",
                                              "RIOT_TERMINAL=picocom"),
                                 f"./dist/tools/term/term.py {recipe} -C "
                                 "'examples/basic/hello-world' BOARD='nrf52840dk' "
                                 "RIOT_TERMINAL=picocom")
        self.assertEqual(self.dry_run("generate-term-data"), "./dist/tools/term/term.py generate")

    def test_same_parameters_as_flash(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        self.assertEqual(names("term"), names("flash"))
        self.assertEqual(names("cleanterm"), names("flash"))
        self.assertTrue(recipes["generate-term-data"]["private"])
        self.assertFalse(recipes["term"]["private"])


class MakeKeepsTermTest(unittest.TestCase):
    """R3: the rules."""

    def test_term_and_cleanterm_rules(self):
        with open(os.path.join(sample.RIOTBASE, "Makefile.include"), encoding="utf-8") as file:
            text = file.read()
        self.assertIn("term: $(TERMDEPS)\n\t$(call check_cmd,$(TERMPROG),Terminal program)\n"
                      "\t${TERMENV} $(TERMPROG) $(TERMFLAGS) $(TERMTEE)\n", text)
        self.assertIn("cleanterm: export PYTERMFLAGS += --no-reconnect --noprefix "
                      "--no-repeat-command-on-empty-line\ncleanterm: $(TERMDEPS)\n"
                      "\t$(call check_cmd,$(TERMPROG),Terminal program)\n"
                      "\t$(TERMPROG) $(TERMFLAGS) $(TERMTEE)\n", text)
        self.assertIn("include $(RIOTMAKE)/tools/serial.inc.mk\n", text)
        self.assertIn("include $(RIOTMAKE)/term_providers.inc.mk\n", text)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """R3: live Make with the adapters = golden."""

    def check(self, app: str):
        for name, c in sample.cases(app).items():
            case = harness.Case(sample.APPS[app], c)
            try:
                g_status, g_lines = harness.golden(app, name, "dry-run")
                res = case.make(["-n", c["goal"]])
                lines = [line for line in case.norm(res.stdout + res.stderr).split("\n") if line]
                with self.subTest(app=app, case=name, what="make -n"):
                    self.assertEqual(res.returncode, g_status)
                    if g_status == 0:
                        self.assertEqual(lines, g_lines)
                    else:   # the line of $(error) names the adapter now
                        self.assertEqual([l.split("*** ", 1)[1] for l in lines],
                                         [l.split("*** ", 1)[1] for l in g_lines])
                if g_status != 0 or not harness.uses_path_or_image(case, g_lines):
                    continue
                t_status, t_lines = harness.golden(app, name, "terminal call")
                case.clear_logs()
                sample.fake_image(case.bindir, case.app_dir)
                res = case.make([c["goal"]])
                out = [f"out: {line}" for line in case.norm(res.stdout + res.stderr).split("\n")
                       if line and not line.startswith("make: ***")]
                with self.subTest(app=app, case=name, what="terminal call"):
                    self.assertEqual(res.returncode, t_status)
                    self.assertEqual(out + case.logs(), t_lines)
            finally:
                case.cleanup()

    def test_hello_world(self):
        self.check("hello-world")

    def test_gnrc_networking(self):
        self.check("gnrc_networking")

    def test_bindist(self):
        self.check("bindist")


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(sample.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g2b-01-term"]
        self.assertEqual(step["group"], "2B")
        self.assertEqual(step["tests"], ["dist/tools/term/tests"])
        self.assertEqual(step["docs"], "dist/tools/term/README.md")
        targets = {t["name"]: t for t in step["targets"]}
        self.assertEqual(sorted(targets), ["cleanterm", "term"])
        for name, target in targets.items():
            with self.subTest(target=name):
                self.assertTrue(target["hardware"])
                self.assertTrue(target["now"].startswith(f"just {name} <application> <board>"))
                self.assertIn("nRF52840", target["board_test"])
                self.assertIn("make", target["board_test"])


if __name__ == "__main__":
    unittest.main()
