#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""R1, R3, O1: how `debug`, `debug-server` and `debug-client` move out of
Make.

R1 `just debug|debug-server|debug-client <app> <board> [VAR=VALUE…]` run
   debug.py (same parameters as `just flash`)
R3 Make keeps the three rules (D6, applications, boards and programmers
   outside the data); live Make, which now reads the generated debug.inc.mk,
   gives the golden output of the base for every case (`make -n` and the run)
O1 the register lists step g2b-02-debug: group 2B, the three targets,
   hardware, with a board test
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
import debug_sample as S  # noqa: E402
import test_parity as TP  # noqa: E402

JUST = shutil.which("just")
MAKE = shutil.which("make")


@unittest.skipIf(JUST is None, "just is not installed")
class JustTest(unittest.TestCase):
    """R1."""

    def test_recipes(self):
        for recipe in S.GOALS:
            res = subprocess.run([JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"),
                                  "--dry-run", recipe, "examples/basic/hello-world",
                                  "nrf52840dk", "PROGRAMMER=jlink"], cwd=S.RIOTBASE,
                                 capture_output=True, text=True, check=True)
            with self.subTest(recipe=recipe):
                self.assertEqual(res.stderr.strip(),
                                 f"./dist/tools/debug/debug.py {recipe} -C "
                                 "'examples/basic/hello-world' BOARD='nrf52840dk' "
                                 "PROGRAMMER=jlink")

    def test_same_parameters_as_flash(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True, text=True,
                             check=True)
        recipes = yaml.safe_load(res.stdout)["recipes"]
        names = lambda r: [p["name"] for p in recipes[r]["parameters"]]  # noqa: E731
        for recipe in S.GOALS:
            self.assertEqual(names(recipe), names("flash"))
            self.assertFalse(recipes[recipe]["private"])


class MakeKeepsDebugTest(unittest.TestCase):
    """R3: the rules."""

    def test_rules(self):
        with open(os.path.join(S.RIOTBASE, "Makefile.include"), encoding="utf-8") as file:
            text = file.read()
        for goal, (var, flags, what) in (("debug", ("DEBUGGER", "DEBUGGER_FLAGS",
                                                   "Debug program")),
                                         ("debug-client", ("DEBUGCLIENT", "DEBUGCLIENT_FLAGS",
                                                          "Debug client program")),
                                         ("debug-server", ("DEBUGSERVER", "DEBUGSERVER_FLAGS",
                                                          "Debug server program"))):
            with self.subTest(goal=goal):
                self.assertIn(f"ifeq (, $({var}))\n{goal}:\n", text)
                self.assertIn(f"{goal}: $(DEBUGDEPS)\n\t$(call check_cmd,$({var}),{what})\n"
                              f"\t$({var}) $({flags})\n", text)
        # D11: debug-client is not .PHONY at the base and stays so
        phony = [l for l in text.split("\n") if l.startswith(".PHONY:") and " debug " in l][0]
        self.assertNotIn("debug-client", phony)


def make(run, option):
    return run.make_argv(["-n", run.c["goal"]] if option == "-n" else [run.c["goal"]])


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """R3: live Make with the adapters = golden."""

    def check(self, app: str):
        for name, c in S.cases(app).items():
            if not c["record"]:
                continue
            if c["outside"] or c["error"]:     # `make -n` only
                g_status, g_lines = TP.golden(app, name, "dry-run")
                with tempfile.TemporaryDirectory(prefix="g2b-debug-") as tmp:
                    run = S.Run(S.RIOTBASE, S.APPS[app], c, tmp)
                    status, out, err = run.capture(make(run, "-n"))
                    lines = [l for l in run.norm(out + err).split("\n") if l]
                with self.subTest(app=app, case=name):
                    self.assertEqual(status, g_status)
                    if c["error"]:   # Makefile.include has one comment line more
                        lines = [l.split(": ", 1)[1] for l in lines]
                        g_lines = [l.split(": ", 1)[1] for l in g_lines]
                    self.assertEqual(lines, g_lines)
                continue
            TP.check_case(self, app, name, c, make)

    def test_hello_world(self):
        self.check("hello-world")

    def test_gnrc_networking(self):
        self.check("gnrc_networking")

    def test_bindist(self):
        self.check("bindist")


class RegisterTest(unittest.TestCase):
    """O1."""

    def test_step(self):
        with open(os.path.join(S.RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {s["id"]: s for s in yaml.safe_load(file)["steps"]}
        step = steps["g2b-02-debug"]
        self.assertEqual(step["group"], "2B")
        self.assertEqual(step["tests"], ["dist/tools/debug/tests"])
        self.assertEqual(step["docs"], "dist/tools/debug/README.md")
        targets = {t["name"]: t for t in step["targets"]}
        self.assertEqual(sorted(targets), sorted(S.GOALS))
        for name, target in targets.items():
            with self.subTest(target=name):
                self.assertTrue(target["hardware"])
                self.assertTrue(target["now"].startswith(f"just {name} <application> <board>"))
                self.assertIn("make", target["board_test"])


if __name__ == "__main__":
    unittest.main()
