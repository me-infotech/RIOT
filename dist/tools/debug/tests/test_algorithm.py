#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A5: the algorithm of debug.py, case by case.

A1 the recipe of the three goals: check_cmd with the description of each
   goal and Make's colours; the hint of a program that is not set (the
   continued lines as the shell gets them) followed by `false`
A2 exit 3 for DEBUGDEPS (USE_PYCORTEXMDEBUG=1: nothing fetched; EMULATE=1:
   no mktemp directory; macOS without setsid: nothing built), a programmer
   without debugger data (pyocd; one with flash data only), a board without
   terminal data (native64)
A3 exit 2: Make's `$(error)` of an empty FLASHFILE (unknown programmer),
   a missing debugger (check_cmd), the hint; no `make: ***` line
A4 the target exports of the goal, patterns included (`debug%` covers
   debug-server and debug-client, not debug, as Make's pattern-specific
   variables)
A5 the variables of the environment as Make takes them (PROGRAMMER)
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import debug_sample as S  # noqa: E402
import debug as D  # noqa: E402
import term as TM  # noqa: E402

HELLO = os.path.join(S.RIOTBASE, S.APPS["hello-world"])


class FakeVariables:
    def __init__(self, **values):
        self.values = values

    def get(self, name):
        return self.values.get(name, "")


def cli(goal, *variables, env=None, path=None):
    with tempfile.TemporaryDirectory(prefix="g2b-debug-") as tmp:
        environ = {"PATH": path or os.environ["PATH"], "HOME": tmp, "LC_ALL": "C",
                   "TMPDIR": tmp, **(env or {})}
        res = subprocess.run([sys.executable, S.CLI, goal, "-C", HELLO, *variables],
                             env=environ, capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, check=False)
        left = os.listdir(tmp)
    return res, left


class RecipeTest(unittest.TestCase):
    """A1."""

    def test_check_line_per_goal(self):
        v = FakeVariables(DEBUGGER="dbg", DEBUGGER_FLAGS="debug x.elf", DEBUGSERVER="srv",
                          DEBUGSERVER_FLAGS="debug-server", DEBUGCLIENT="cli",
                          DEBUGCLIENT_FLAGS="debug-client x.elf")
        for goal, prog, flags, what in (("debug", "dbg", "debug x.elf", "Debug program"),
                                        ("debug-server", "srv", "debug-server",
                                         "Debug server program"),
                                        ("debug-client", "cli", "debug-client x.elf",
                                         "Debug client program")):
            with self.subTest(goal=goal):
                lines, sh = D.recipe(v, goal, isatty=lambda fd: False)
                self.assertEqual(sh, "/bin/sh")
                self.assertEqual(lines, [
                    f"@command -v {prog} >/dev/null 2>&1 || {{ /usr/bin/env echo '{what} "
                    f"{prog} is required but not found in PATH.  Aborting.'; exit 1;}}",
                    f"{prog} {flags}"])

    def test_colours(self):
        v = FakeVariables(DEBUGGER="dbg")
        lines, _ = D.recipe(v, "debug", isatty=lambda fd: True)
        self.assertIn(r"'\033[1;31mDebug program dbg is required", lines[0])
        self.assertIn(r"Aborting.\033[0m'", lines[0])
        lines, sh = D.recipe(FakeVariables(DEBUGGER="dbg", OS="Darwin"), "debug",
                             isatty=lambda fd: True)
        self.assertEqual(sh, "bash")
        self.assertIn("{ echo -e '", lines[0])

    def test_not_set(self):
        for goal, var in (("debug", "DEBUGGER"), ("debug-server", "DEBUGSERVER"),
                          ("debug-client", "DEBUGCLIENT")):
            with self.subTest(goal=goal):
                lines, _ = D.recipe(FakeVariables(), goal, isatty=lambda fd: False)
                self.assertEqual(lines[1], "@false")
                out = subprocess.run(["/bin/sh", "-c", lines[0][1:]], capture_output=True,
                                     text=True, check=True).stdout
                self.assertEqual(out, f"$({var}) is not set. This means that `make debug` is "
                                 "not supported by your current setup. A common reason is "
                                 "that PROGRAMMER is set to something like flashing via "
                                 "bootloader, where debugging is not possible.\n")


class OutsideTest(unittest.TestCase):
    """A2."""

    def test_exit_3(self):
        nosetsid = tempfile.TemporaryDirectory(prefix="g2b-debug-")   # pylint: disable=consider-using-with
        try:
            path = os.pathsep.join([S.system_without_setsid(nosetsid.name)])
            for goal, variables, path_, why in (
                    ("debug", ["USE_PYCORTEXMDEBUG=1"], None, "PyCortexMDebug/checkout"),
                    ("debug-client", ["EMULATE=1"], None, "EMULATE=1"),
                    ("debug", ["OS=Darwin", "PROGRAMMER=openocd"], path, "setsid/setsid"),
                    ("debug", ["PROGRAMMER=pyocd"], None, "pyocd"),
                    ("debug", ["BOARD=native64"], None, "native64")):
                board = [] if any(v.startswith("BOARD=") for v in variables) \
                    else [f"BOARD={S.BOARD}"]
                with self.subTest(variables=variables):
                    res, left = cli(goal, *board, *variables, path=path_)
                    self.assertEqual(res.returncode, 3, res.stderr)
                    self.assertIn(why, res.stderr)
                    self.assertEqual(left, [])                  # no mktemp directory
            for made in ("dist/tools/PyCortexMDebug/checkout", "dist/tools/setsid/setsid",
                         "dist/tools/setsid/bin"):
                self.assertFalse(os.path.exists(os.path.join(S.RIOTBASE, made)), made)
        finally:
            nosetsid.cleanup()

    def test_programmer_with_flash_but_without_debugger_data(self):
        with tempfile.TemporaryDirectory(prefix="g2b-debug-") as tmp:
            tools_dir = os.path.join(tmp, "tools")
            os.makedirs(tools_dir)
            for name in ("x.inc.mk", "x.flash.yaml", "y.inc.mk", "y.debug.yaml"):
                open(os.path.join(tools_dir, name), "w", encoding="utf-8").close()
            with self.assertRaises(D.OutOfScope):
                D.check_programmer(FakeVariables(PROGRAMMER="x", RIOTMAKE=tmp))
            D.check_programmer(FakeVariables(PROGRAMMER="y", RIOTMAKE=tmp))
            D.check_programmer(FakeVariables(PROGRAMMER="z", RIOTMAKE=tmp))   # no file: Make's hint

    def test_darwin_debug_server_runs_without_setsid_rule(self):
        res, _ = cli("debug-server", "-n", f"BOARD={S.BOARD}", "OS=Darwin",
                     "PROGRAMMER=openocd")
        self.assertEqual(res.returncode, 0, res.stderr)


class ErrorTest(unittest.TestCase):
    """A3."""

    def test_exit_2(self):
        res, _ = cli("debug", f"BOARD={S.BOARD}", "PROGRAMMER=nosuch")
        self.assertEqual(res.returncode, 2)
        self.assertIn("error: FLASHFILE is not defined for this board: nrf52840dk", res.stderr)
        res, _ = cli("debug", f"BOARD={S.BOARD}", "DEBUGGER=no-such-debugger")
        self.assertEqual((res.returncode, res.stdout.strip()),
                         (2, "Debug program no-such-debugger is required but not found in "
                          "PATH.  Aborting."))
        res, _ = cli("debug-client", f"BOARD={S.BOARD}", "PROGRAMMER=jlink")
        self.assertEqual(res.returncode, 2)
        self.assertTrue(res.stdout.startswith("$(DEBUGCLIENT) is not set."))
        self.assertNotIn("make: ***", res.stdout + res.stderr)


class ExportTest(unittest.TestCase):
    """A4."""

    def test_target_matches(self):
        self.assertTrue(TM.target_matches("debug-server", "debug%"))
        self.assertTrue(TM.target_matches("debug-client", "debug%"))
        self.assertFalse(TM.target_matches("debug", "debug%"))
        self.assertTrue(TM.target_matches("debug", "debug"))
        self.assertFalse(TM.target_matches("flash", "flash-only"))
        self.assertTrue(TM.target_matches("a-x-b", "a%b"))

    def test_environment_per_goal(self):
        envs = {}
        for goal in S.GOALS:
            r = D.plan_debug(HELLO, {"BOARD": S.BOARD, "PROGRAMMER": "openocd"}, goal, {})
            envs[goal] = r["env"]
        self.assertNotIn("GDB_PORT_CORE_OFFSET", envs["debug"])
        self.assertEqual(envs["debug-server"]["GDB_PORT_CORE_OFFSET"], "")
        self.assertEqual(envs["debug-client"]["GDB_PORT_CORE_OFFSET"], "")


class EnvironmentTest(unittest.TestCase):
    """A5."""

    def test_programmer_from_the_environment(self):
        r = D.plan_debug(HELLO, {"BOARD": S.BOARD}, "debug", {"PROGRAMMER": "bmp"})
        self.assertIn("dist/tools/bmp/bmp.py", r["recipe"][1])
        self.assertEqual(r["env"]["PROGRAMMER"], "bmp")
        r = D.plan_debug(HELLO, {"BOARD": S.BOARD, "PROGRAMMER": "jlink"}, "debug",
                         {"PROGRAMMER": "bmp"})
        self.assertIn("dist/tools/jlink/jlink.sh", r["recipe"][1])


if __name__ == "__main__":
    unittest.main()
