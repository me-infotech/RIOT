#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""I1-I5: the terminal behaves like `make term` while it runs (E7), with a
stub terminal (picocom) on PATH; each check runs the same scenario with
term.py and with live GNU Make (which reads the generated adapters):

I1 stdin reaches the terminal (pipe)
I2 a terminal started from a pty sees a tty on stdin and stdout
I3 Ctrl+C (SIGINT to the process group): the program ends by SIGINT, as
   Make, and no terminal process is left (also through `just term`)
I4 SIGTERM to the program alone: passed on to the shell of the recipe line,
   the program ends by SIGTERM; the terminal process stays, as with Make
I5 exit status: 0, 2 when the terminal fails or is missing
"""

import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402

MAKE = shutil.which("make")
JUST = shutil.which("just")
CLI = os.path.join(sample.TOOL, "term.py")
STUB = """#!/bin/sh
# stub terminal (step G2B-1, interactive tests)
echo $$ > "$G2B_PIDFILE"
if [ -t 0 ]; then t0=tty; else t0=pipe; fi
if [ -t 1 ]; then t1=tty; else t1=pipe; fi
[ -n "$G2B_TTYFILE" ] && { echo "$t0 $t1" > "$G2B_TTYFILE"; exit 0; }
[ -n "$G2B_TERM_STDIN" ] && { cat > "$G2B_TERM_STDIN"; exit 0; }
[ -n "$G2B_EXIT" ] && exit "$G2B_EXIT"
while :; do sleep 0.05; done
"""
TOOLS = ("term.py", "make")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:   # a zombie is not a leftover process
        with open(f"/proc/{pid}/stat", encoding="utf-8") as file:
            return file.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return True


class Scenario:
    """A temporary PATH with the stub picocom (or none) and the files it
    writes."""

    def __init__(self, stub=True):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2b-term-i-")   # pylint: disable=consider-using-with
        root = self.tmp.name
        self.bin = os.path.join(root, "bin")
        os.makedirs(self.bin)
        if stub:
            sample.write_executable(os.path.join(self.bin, "picocom"), STUB)
        self.pidfile = os.path.join(root, "pid")
        self.env = {"PATH": self.bin + os.pathsep + "/usr/local/bin:/usr/bin:/bin",
                    "HOME": root, "LC_ALL": "C", "USER": sample.USER, "TMPDIR": root,
                    "G2B_PIDFILE": self.pidfile}

    def argv(self, tool: str) -> list:
        if tool == "make":
            return ["make", "--no-print-directory", "-C", sample.APPS["hello-world"],
                    f"BOARD={sample.BOARD}", "RIOT_TERMINAL=picocom", "term"]
        if tool == "just":
            return [JUST, "term", sample.APPS["hello-world"], sample.BOARD,
                    "RIOT_TERMINAL=picocom"]
        return [sys.executable, CLI, "term", "-C", sample.APPS["hello-world"],
                f"BOARD={sample.BOARD}", "RIOT_TERMINAL=picocom"]

    def path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def read(self, name: str) -> str:
        with open(self.path(name), encoding="utf-8") as file:
            return file.read()

    def terminal_pid(self, timeout=20.0) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if os.path.exists(self.pidfile):
                with open(self.pidfile, encoding="utf-8") as file:
                    text = file.read().strip()
                if text:
                    return int(text)
            time.sleep(0.05)
        raise AssertionError("the terminal did not start")

    def cleanup(self):
        self.tmp.cleanup()


def tools():
    return [t for t in TOOLS if t != "make" or MAKE]


class StdinTest(unittest.TestCase):
    """I1."""

    def test_pipe(self):
        for tool in tools():
            s = Scenario()
            try:
                env = dict(s.env, G2B_TERM_STDIN=s.path("stdin"))
                res = subprocess.run(s.argv(tool), input="help\nps\n", env=env, text=True,
                                     cwd=sample.RIOTBASE, capture_output=True, timeout=60,
                                     check=False)
                with self.subTest(tool=tool):
                    self.assertEqual(res.returncode, 0, res.stderr)
                    self.assertEqual(s.read("stdin"), "help\nps\n")
            finally:
                s.cleanup()


class PtyTest(unittest.TestCase):
    """I2."""

    def test_tty(self):
        for tool in tools():
            s = Scenario()
            master, slave = pty.openpty()
            try:
                env = dict(s.env, G2B_TTYFILE=s.path("tty"))
                proc = subprocess.Popen(s.argv(tool), stdin=slave, stdout=slave, stderr=slave,   # pylint: disable=consider-using-with
                                        env=env, cwd=sample.RIOTBASE)
                os.close(slave)
                end = time.monotonic() + 60
                while proc.poll() is None and time.monotonic() < end:
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            os.read(master, 4096)
                        except OSError:
                            break
                proc.wait(timeout=30)
                with self.subTest(tool=tool):
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(s.read("tty").strip(), "tty tty")
            finally:
                os.close(master)
                s.cleanup()


class SignalTest(unittest.TestCase):
    """I3, I4."""

    def run_and_signal(self, tool: str, group: bool, sig: int) -> tuple:
        s = Scenario()
        try:
            proc = subprocess.Popen(s.argv(tool), env=s.env, cwd=sample.RIOTBASE,   # pylint: disable=consider-using-with
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
            pid = s.terminal_pid()
            if group:
                os.killpg(proc.pid, sig)
            else:
                os.kill(proc.pid, sig)
            status = proc.wait(timeout=30)
            time.sleep(0.2)
            left = alive(pid)
            if left:
                os.kill(pid, signal.SIGKILL)
            return status, left
        finally:
            s.cleanup()

    def test_ctrl_c(self):
        results = {tool: self.run_and_signal(tool, True, signal.SIGINT) for tool in tools()}
        self.assertEqual(results["term.py"], (-signal.SIGINT, False))
        if MAKE:
            self.assertEqual(results["make"], results["term.py"])

    @unittest.skipIf(JUST is None, "just is not installed")
    def test_ctrl_c_through_just(self):
        status, left = self.run_and_signal("just", True, signal.SIGINT)
        self.assertIn(status, (-signal.SIGINT, 128 + signal.SIGINT))
        self.assertFalse(left)

    def test_sigterm(self):
        # Make passes SIGTERM to the shell of the recipe line, not to the
        # terminal it started; the terminal stays, as with Make (stopped here)
        results = {tool: self.run_and_signal(tool, False, signal.SIGTERM) for tool in tools()}
        self.assertEqual(results["term.py"][0], -signal.SIGTERM)
        if MAKE:
            self.assertEqual(results["make"], results["term.py"])


class ExitStatusTest(unittest.TestCase):
    """I5."""

    def status(self, tool: str, stub=True, **env) -> int:
        s = Scenario(stub)
        try:
            return subprocess.run(s.argv(tool), env=dict(s.env, **env), cwd=sample.RIOTBASE,
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                                  check=False).returncode
        finally:
            s.cleanup()

    def test_exit_status(self):
        if shutil.which("picocom", path="/usr/local/bin:/usr/bin:/bin"):
            self.skipTest("a real picocom is installed")
        for tool in tools():
            with self.subTest(tool=tool):
                self.assertEqual(self.status(tool, G2B_EXIT="0"), 0)
                self.assertEqual(self.status(tool, G2B_EXIT="3"), 2)
                self.assertEqual(self.status(tool, stub=False), 2)


if __name__ == "__main__":
    unittest.main()
