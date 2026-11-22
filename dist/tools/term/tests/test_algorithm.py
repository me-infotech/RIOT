#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A8: the algorithm of term.py, case by case.

A1 the value `word` (firstword, lastword, word N)
A2 the condition `command: {name}` asks the shell
A3 the probes: Make's `$(shell …)` (newlines, fallback), date, ttys.py,
   the macOS modems, `$(GDBPREFIX)gdb -v`
A4 variables of the environment as Make takes them (`?=` keeps, `=`
   replaces, the command line wins) and passes them on
A5 the order of reading (flash before debugger before terminal data, the
   programmer after the CPU, serial.inc.mk after the programmer)
A6 exit 3 outside the data: bootterm (TERMDEPS), EMULATE=1 (no mktemp
   directory left), IOTLAB_NODE, a board without terminal data (native64),
   a programmer without data
A7 the recipe: check_cmd line with Make's colours (terminal or not, macOS,
   CC_NOCOLOR), TERMTEE, cleanterm's PYTERMFLAGS, TERMENV only for term
A8 the terminal data alone: stdio_rtt (openocd, jlink, warning), the
   miniterm search, the ports of MOST_RECENT_PORT, macOS and bmp
"""

import glob
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import term  # noqa: E402
import termdata as T  # noqa: E402
import sample  # noqa: E402

HELLO = os.path.join(sample.RIOTBASE, sample.APPS["hello-world"])
SERIAL = os.path.join(sample.RIOTBASE, "makefiles", "tools", "serial.term.yaml")
BASE_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent",
            "USER": sample.USER, "LC_ALL": "C"}


def evaluate(variables=None, environ=None):
    return term.evaluate(HELLO, dict({"BOARD": sample.BOARD}, **(variables or {})),
                         dict(environ if environ is not None else BASE_ENV))


def run_serial(**values):
    """The terminal data of serial.inc.mk alone on the given values."""
    v = term.TermVariables(term.PROVIDERS)
    for name, value in values.items():
        v.set(name, value)
    ev = term.TermEvaluator(v, sample.RIOTBASE)
    ev.run_file(SERIAL)
    return ev


def cli(*args, env=None):
    return subprocess.run([sys.executable, os.path.join(sample.TOOL, "term.py"), *args],
                          cwd=sample.RIOTBASE, env=env or BASE_ENV, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, check=False)


class WordTest(unittest.TestCase):
    """A1."""

    def test_word(self):
        v = term.TermVariables()
        v.set("T", "a b c")
        v.set("E", "")
        for index, var, expected in ((1, "T", "a"), (-1, "T", "c"), (2, "T", "b"),
                                     (3, "T", "c"), (4, "T", ""), (1, "E", ""), (-1, "E", ""),
                                     (2, "U", "")):
            with self.subTest(index=index, var=var):
                self.assertEqual(v.term({"word": {"var": var, "index": index}}), expected)


class CommandNameTest(unittest.TestCase):
    """A2."""

    def test_command_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample.write_executable(os.path.join(tmp, "miniterm"), "#!/bin/sh\n")
            ev = term.TermEvaluator(term.TermVariables(), sample.RIOTBASE)
            with mock.patch.dict(os.environ, {"PATH": tmp + os.pathsep + "/usr/bin:/bin"}):
                self.assertTrue(ev.condition({"command": {"name": "miniterm"}}))
                self.assertFalse(ev.condition({"command": {"name": "miniterm.py"}}))
                self.assertTrue(ev.condition({"not": {"command": {"name": "miniterm.py"}}}))


class ProbeTest(unittest.TestCase):
    """A3."""

    def test_shell_like_make(self):
        self.assertEqual(term.shell("printf 'a\\nb\\n\\n'"), "a b")
        self.assertEqual(term.shell("printf 'a\\r\\nb'"), "a b")
        self.assertEqual(term.shell("exit 1"), "")

    def test_tty_detected(self):
        v = term.TermVariables()
        v.set("TTY_SELECT_CMD", "printf '/dev/ttyACM3\\nABC\\n'")
        self.assertEqual(term.probe_tty_detected(v), "/dev/ttyACM3 ABC")
        v = term.TermVariables()
        v.set("TTY_SELECT_CMD", "false")
        self.assertEqual(term.probe_tty_detected(v), "no-tty-detected no-serial-detected")

    def test_date_and_gdb_from_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample.make_stubs(tmp, ())
            sample.write_executable(os.path.join(tmp, "probe", "xgdb"), "#!/bin/sh\nexit 0\n")
            v = term.TermVariables()
            v.set("GDBPREFIX", "x")
            with mock.patch.dict(os.environ, {"PATH": os.path.join(tmp, "probe") + ":/usr/bin:/bin"}):
                self.assertEqual(term.probe_date_time(v), sample.DATE)
                self.assertEqual(term.probe_gdb_status(v), "0")
                v.set("GDBPREFIX", "nonexistent-prefix-")
                self.assertEqual(term.probe_gdb_status(v), "127")

    def test_date_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample.write_executable(os.path.join(tmp, "date"), '#!/bin/sh\necho "$@"\n')
            with mock.patch.dict(os.environ, {"PATH": tmp + ":/usr/bin:/bin"}):
                self.assertEqual(term.probe_date_time(None), "+%Y-%m-%d_%H.%M.%S")

    def test_usbmodem_sorted(self):
        with mock.patch.object(glob, "glob", return_value=["/dev/tty.usbmodem2",
                                                           "/dev/tty.usbmodem1",
                                                           "/dev/tty.usbmodem2"]):
            self.assertEqual(term.probe_tty_usbmodem(None),
                             "/dev/tty.usbmodem1 /dev/tty.usbmodem2")


class EnvironmentTest(unittest.TestCase):
    """A4."""

    def test_conditional_keeps_the_environment(self):
        v = evaluate(environ=dict(BASE_ENV, PORT="/dev/ttyUSB9", RIOT_TERMINAL="picocom")).v
        self.assertEqual(v.get("PORT"), "/dev/ttyUSB9")
        self.assertEqual(v.get("TERMPROG"), "picocom")

    def test_assignment_replaces_and_command_line_wins(self):
        v = evaluate({"RIOT_TERMINAL": "jlink", "PROGRAMMER": "jlink"},
                     dict(BASE_ENV, TERMPROG="mine", PORT="/dev/env")).v
        self.assertEqual(v.get("TERMPROG"), os.path.join(sample.RIOTBASE, "dist/tools/jlink/jlink.sh"))
        v = evaluate({"PORT": "/dev/cmdline"}, dict(BASE_ENV, PORT="/dev/env")).v
        self.assertEqual(v.get("PORT"), "/dev/cmdline")

    def test_environment_reaches_the_terminal_with_makes_value(self):
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD}, "cleanterm",
                                dict(BASE_ENV, PYTERMFLAGS="-y"))
        self.assertEqual(result["env"]["PYTERMFLAGS"], "-y " + term.CLEANTERM_PYTERMFLAGS)
        self.assertEqual(result["env"]["USER"], sample.USER)

    def test_replaced_variable_reaches_the_terminal_with_makes_value(self):
        # GNU Make exports a variable of the environment that a Make file
        # replaces with its new value
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD, "RIOT_TERMINAL": "jlink",
                                        "PROGRAMMER": "jlink"}, "term",
                                dict(BASE_ENV, TERMPROG="mine"))
        self.assertEqual(result["env"]["TERMPROG"],
                         os.path.join(sample.RIOTBASE, "dist/tools/jlink/jlink.sh"))

    def test_not_imported(self):
        v = evaluate(environ=dict(BASE_ENV, SHELL="/bin/zsh", MAKEFLAGS="-k")).v
        self.assertFalse(v.defined("SHELL"))
        self.assertFalse(v.defined("MAKEFLAGS"))


class OrderTest(unittest.TestCase):
    """A5."""

    def test_read_order(self):
        for programmer in ("jlink", "openocd", "bmp"):
            with self.subTest(programmer=programmer):
                read = evaluate({"PROGRAMMER": programmer}).read
                pos = read.index
                self.assertLess(pos("boards/nrf52840dk/flash.yaml"), pos("boards/nrf52840dk/term.yaml"))
                self.assertLess(pos("boards/nrf52840dk/term.yaml"), pos("boards/nrf52840dk/build.yaml"))
                self.assertLess(pos("boards/common/nrf52/flash.yaml"),
                                pos("boards/common/nrf52/term.yaml"))
                self.assertLess(pos("cpu/nrf52/build.yaml"),
                                pos(f"makefiles/tools/{programmer}.flash.yaml"))
                self.assertLess(pos(f"makefiles/tools/{programmer}.flash.yaml"),
                                pos(f"makefiles/tools/{programmer}.debug.yaml"))
                self.assertLess(pos(f"makefiles/tools/{programmer}.debug.yaml"),
                                pos("makefiles/tools/serial.term.yaml"))
                self.assertLess(pos("makefiles/tools/serial.term.yaml"),
                                pos("makefiles/toolchain/gnu.debug.yaml"))
                self.assertLess(pos("makefiles/toolchain/gnu.debug.yaml"),
                                pos("makefiles/tools/gdb.debug.yaml"))
                self.assertLess(pos("makefiles/tools/gdb.debug.yaml"), pos("debug.yaml"))
                if programmer != "bmp":
                    self.assertIn("makefiles/tools/dbg_common.debug.yaml", read)

    def test_dbg_common_once(self):
        read = evaluate({"PROGRAMMER": "openocd"}).read
        self.assertEqual(read.count("makefiles/tools/dbg_common.debug.yaml"), 1)


class ScopeTest(unittest.TestCase):
    """A6."""

    def test_outside_the_data(self):
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "riot_*")))
        for args, text in (
                (["RIOT_TERMINAL=bootterm"], "dist/tools/bootterm/bt to be built first"),
                (["EMULATE=1"], "EMULATE=1"),
                (["IOTLAB_NODE=auto"], "IOTLAB_NODE=auto"),
                (["PROGRAMMER=pyocd"], "programmer pyocd"),
                (["RIOT_TERMINAL=native", "BOARD=native64"], "board native64")):
            board = [] if any(a.startswith("BOARD=") for a in args) else [f"BOARD={sample.BOARD}"]
            with self.subTest(args=args):
                res = cli("term", "-n", "-C", HELLO, *board, *args)
                self.assertEqual(res.returncode, 3, res.stderr)
                self.assertIn(text, res.stderr)
                self.assertEqual(res.stdout, "")
        self.assertEqual(set(glob.glob(os.path.join(tempfile.gettempdir(), "riot_*"))), before)

    def test_configuration_error_is_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = cli("term", "-n", "-C", HELLO, f"BOARD={sample.BOARD}", "RIOT_TERMINAL=miniterm",
                      env=dict(BASE_ENV, PATH=tmp + ":/usr/bin:/bin"))
        if any(os.path.exists(os.path.join(d, n)) for d in ("/usr/bin", "/bin")
               for n in ("pyserial-miniterm.py", "pyserial-miniterm", "miniterm.py", "miniterm")):
            self.skipTest("a miniterm is installed")
        self.assertEqual(res.returncode, 2)
        self.assertIn("The pyserial miniterm was not found! Check if pyserial is installed.",
                      res.stderr)
        self.assertNotIn("make: ***", res.stderr)


class RecipeTest(unittest.TestCase):
    """A7."""

    def v(self, **values):
        v = term.TermVariables()
        for name, value in dict({"TERMPROG": "picocom", "TERMFLAGS": "-b 1",
                                 "TERMENV": "A=1", "OS": "Linux"}, **values).items():
            v.set(name, value)
        return v

    def test_check_line_and_colours(self):
        tty, pipe = (lambda fd: True), (lambda fd: False)
        lines, sh = term.recipe(self.v(), "term", pipe)
        self.assertEqual(lines, [
            "@command -v picocom >/dev/null 2>&1 || { /usr/bin/env echo 'Terminal program "
            "picocom is required but not found in PATH.  Aborting.'; exit 1;}",
            "A=1 picocom -b 1 "])
        self.assertEqual(sh, "/bin/sh")
        lines, sh = term.recipe(self.v(), "term", tty)
        self.assertEqual(lines[0], "@command -v picocom >/dev/null 2>&1 || { /usr/bin/env echo -e "
                         "'\\033[1;31mTerminal program picocom is required but not found in "
                         "PATH.  Aborting.\\033[0m'; exit 1;}")
        lines, sh = term.recipe(self.v(OS="Darwin"), "term", tty)
        self.assertIn("{ echo -e '\\033[1;31m", lines[0])
        self.assertEqual(sh, "bash")
        lines, _ = term.recipe(self.v(CC_NOCOLOR="1"), "term", tty)
        self.assertIn("{ /usr/bin/env echo 'Terminal", lines[0])
        only_out = (lambda fd: fd == 1)
        self.assertIn("{ /usr/bin/env echo 'Terminal", term.recipe(self.v(), "term", only_out)[0][0])

    def test_cleanterm_has_no_termenv(self):
        lines, _ = term.recipe(self.v(), "cleanterm", lambda fd: False)
        self.assertEqual(lines[1], "picocom -b 1 ")

    def test_termtee_and_cleanterm(self):
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD, "TERMLOG": "/tmp/x.log"}, "term",
                                BASE_ENV, isatty=lambda fd: False)
        self.assertTrue(result["recipe"][1].endswith("| tee -a /tmp/x.log"))
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD, "TERMTEE": "| cat"}, "term",
                                BASE_ENV, isatty=lambda fd: False)
        self.assertTrue(result["recipe"][1].endswith(" | cat"))
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD}, "cleanterm", BASE_ENV,
                                isatty=lambda fd: False)
        self.assertTrue(result["recipe"][1].endswith(term.CLEANTERM_PYTERMFLAGS + " "))
        self.assertEqual(result["env"]["PYTERMFLAGS"], term.CLEANTERM_PYTERMFLAGS)
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD, "PYTERMFLAGS": "-x"}, "cleanterm",
                                BASE_ENV, isatty=lambda fd: False)
        self.assertEqual(result["env"]["PYTERMFLAGS"], "-x")
        result = term.plan_term(HELLO, {"BOARD": sample.BOARD}, "term", BASE_ENV)
        self.assertNotIn("PYTERMFLAGS", result["env"])


class SerialDataTest(unittest.TestCase):
    """A8."""

    def test_stdio_rtt(self):
        ev = run_serial(USEMODULE="stdio_rtt", PROGRAMMER="openocd")
        self.assertEqual(ev.v.get("RIOT_TERMINAL"), "openocd-rtt")
        ev = run_serial(USEMODULE="stdio_rtt", PROGRAMMER="jlink")
        self.assertEqual(ev.v.get("RIOT_TERMINAL"), "jlink")
        ev = run_serial(USEMODULE="stdio_rtt", PROGRAMMER="bmp")
        self.assertEqual(ev.v.get("RIOT_TERMINAL"), "pyterm")
        self.assertEqual(ev.messages, [("warning", '"Warning: No RIOT_TERMINAL set, but using '
                                        'stdio_rtt: The default terminal is likely not to work."')])
        ev = run_serial(USEMODULE="stdio_rtt", PROGRAMMER="bmp", RIOT_TERMINAL="socat")
        self.assertEqual((ev.v.get("RIOT_TERMINAL"), ev.messages), ("socat", []))

    def test_miniterm_search_order(self):
        names = ("pyserial-miniterm.py", "pyserial-miniterm", "miniterm.py", "miniterm")
        for i, name in enumerate(names):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(found=names[i:]):
                for other in names[i:]:
                    sample.write_executable(os.path.join(tmp, other), "#!/bin/sh\n")
                with mock.patch.dict(os.environ, {"PATH": tmp + ":/usr/bin:/bin"}):
                    if any(os.path.exists(os.path.join(d, n)) for d in ("/usr/bin", "/bin")
                           for n in names[:i]):
                        self.skipTest("a miniterm is installed")
                    ev = run_serial(RIOT_TERMINAL="miniterm", PORT="/dev/p", BAUD="9")
                self.assertEqual(ev.v.get("TERMPROG"), name)
                self.assertEqual(ev.v.get("TERMFLAGS"), '--eol LF "/dev/p" "9" ')

    def test_most_recent_port(self):
        captured = {}

        def answer(v):
            captured["cmd"] = v.get("TTY_SELECT_CMD")
            return "/dev/ttyACM5 SER"
        with mock.patch.dict(term.PROVIDERS, {"PROBE_TTY_DETECTED": answer}):
            ev = run_serial(MOST_RECENT_PORT="1", TTY_BOARD_FILTER="--model J-Link",
                            DEBUG_ADAPTER_ID_IS_TTY_SERIAL="1", OS="Linux", RIOTTOOLS="/t")
            self.assertEqual(captured["cmd"], "/t/usb-serial/ttys.py --most-recent --format path "
                             "serial --model J-Link")
            self.assertEqual((ev.v.get("PORT"), ev.v.get("DEBUG_ADAPTER_ID"),
                              ev.v.get("PORT_DETECTED")), ("/dev/ttyACM5", "SER", "/dev/ttyACM5"))
            run_serial(MOST_RECENT_PORT="1", USEMODULE="stdio_cdc_acm", BOARD="b", SERIAL="12",
                       PROG_TTY_BOARD_FILTER="--vendor X", RIOTTOOLS="/t")
            self.assertEqual(captured["cmd"], "/t/usb-serial/ttys.py --most-recent --format path "
                             "serial --model 'b' --vendor 'RIOT-os\\.org' --serial \"12\" || "
                             "/t/usb-serial/ttys.py --most-recent --format path serial --vendor X")

    def test_ports(self):
        with mock.patch.dict(term.PROVIDERS, {"PROBE_TTY_USBMODEM":
                                              lambda v: "/dev/tty.usbmodem1 /dev/tty.usbmodem2"}):
            self.assertEqual(run_serial(OS="Linux").v.get("PORT"), "/dev/ttyACM0")
            self.assertEqual(run_serial(OS="Darwin").v.get("PORT"), "/dev/tty.usbmodem1")
            self.assertEqual(run_serial(OS="FreeBSD").v.get("PORT"), "")
            v = evaluate({"PROGRAMMER": "bmp", "OS": "Darwin"}).v
            self.assertEqual(v.get("PORT"), "/dev/tty.usbmodem2")
            v = evaluate({"PROGRAMMER": "bmp"}).v
            self.assertEqual(v.get("PORT"), "/dev/ttyACM1")
            self.assertEqual(v.get("PROG_DEV"), "/dev/ttyACM1")


if __name__ == "__main__":
    unittest.main()
