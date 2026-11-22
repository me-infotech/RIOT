#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""I1-I4: debug.py behaves as live Make while the debugger runs (D7).

Each scenario runs with debug.py and with live Make (the scripts of
dist/tools, the stub tools of debug_sample), in a process group of its own as
a terminal starts it:

I1 openocd, `debug`: Ctrl+C (SIGINT to the process group) leaves GDB
   running (openocd.sh ignores SIGINT for it) and openocd (setsid) and the
   caller waiting; after `quit` the script kills
   openocd and removes its pid file, exits 0, and the caller then ends by
   SIGINT; also through `just debug`
I2 jlink, `debug`: the same Ctrl+C; JLinkGDBServer stays running afterwards
   (Make's behaviour, ended by the test)
I3 openocd, `debug-server`: the server runs while stdin is open; at EOF
   (Ctrl+D) the script kills it and exits 0
I4 SIGTERM to the caller alone: passed to the script's shell, the caller
   ends by SIGTERM, as Make
"""

import os
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
import debug_sample as S  # noqa: E402

MAKE = shutil.which("make")
JUST = shutil.which("just")
APP = S.APPS["hello-world"]


def tools():
    return ["debug.py"] + (["make"] if MAKE else [])


class Scenario:
    """A case of the sample started in a process group of its own."""

    def __init__(self, name: str, tool: str):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2b-debug-")   # pylint: disable=consider-using-with
        self.c = S.CASES[name]
        self.run = S.Run(S.RIOTBASE, APP, self.c, self.tmp.name)
        if tool == "make":
            argv = self.run.make_argv([self.c["goal"]])
        elif tool == "just":
            argv = [JUST, "--justfile", os.path.join(S.RIOTBASE, "justfile"), self.c["goal"],
                    APP, S.BOARD, f"BINDIRBASE={self.run.bindirbase}"] + \
                [f"{k}={v}" for k, v in self.c["vars"].items()]
        else:
            argv = self.run.tool_argv()
        self.proc = subprocess.Popen(argv, cwd=S.RIOTBASE, env=self.run.env(),  # pylint: disable=consider-using-with
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)

    def pids(self, name: str) -> list:
        path = os.path.join(self.run.dbg, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as file:
            return [int(line.split()[1]) for line in file if line.strip()]

    def wait_for(self, name: str, timeout=20.0) -> int:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            pids = self.pids(name)
            if pids:
                return pids[0]
            time.sleep(0.05)
        raise AssertionError(f"{name} did not start")

    def pid_files(self) -> list:
        return [f for f in os.listdir(self.tmp.name) if f.startswith("openocd_pid.")]

    def send(self, text: str, close=True):
        try:
            self.proc.stdin.write(text.encode())
            self.proc.stdin.flush()
            if close:
                self.proc.stdin.close()
        except BrokenPipeError:
            pass

    def cleanup(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()
        self.run.stop_servers()
        for pid in self.pids("gdb.pid"):
            if S.alive(pid):
                os.kill(pid, signal.SIGKILL)
        self.tmp.cleanup()


def ctrl_c_then_quit(name: str, tool: str) -> dict:
    s = Scenario(name, tool)
    try:
        server = s.wait_for("servers.pid")
        gdb = s.wait_for("gdb.pid")
        time.sleep(0.4)
        os.killpg(s.proc.pid, signal.SIGINT)
        time.sleep(0.5)
        during = {"waiting": s.proc.poll() is None, "gdb": S.alive(gdb),
                  "server": S.alive(server)}
        s.send("quit\n")
        status = s.proc.wait(timeout=30)
        time.sleep(0.4)
        return {"during": during, "status": status, "server left": S.alive(server),
                "pid file left": bool(s.pid_files())}
    finally:
        s.cleanup()


class CtrlCTest(unittest.TestCase):
    """I1, I2."""

    def test_openocd(self):
        results = {tool: ctrl_c_then_quit("openocd-debug", tool) for tool in tools()}
        self.assertEqual(results["debug.py"], {
            "during": {"waiting": True, "gdb": True, "server": True},
            "status": -signal.SIGINT, "server left": False, "pid file left": False})
        if MAKE:
            self.assertEqual(results["make"], results["debug.py"])

    @unittest.skipIf(JUST is None, "just is not installed")
    def test_openocd_through_just(self):
        result = ctrl_c_then_quit("openocd-debug", "just")
        self.assertIn(result["status"], (-signal.SIGINT, 128 + signal.SIGINT))
        self.assertEqual((result["server left"], result["pid file left"]), (False, False))

    def test_jlink_server_orphaned_as_make(self):
        results = {tool: ctrl_c_then_quit("jlink-debug", tool) for tool in tools()}
        self.assertEqual(results["debug.py"]["status"], -signal.SIGINT)
        self.assertTrue(results["debug.py"]["server left"])
        if MAKE:
            self.assertEqual(results["make"], results["debug.py"])


def server_until_eof(tool: str) -> dict:
    s = Scenario("openocd-debug-server", tool)
    try:
        server = s.wait_for("servers.pid")
        time.sleep(1.0)
        running = s.proc.poll() is None and S.alive(server)
        s.send("x\n", close=False)
        time.sleep(0.3)
        s.send("")
        status = s.proc.wait(timeout=30)
        time.sleep(0.4)
        return {"running while stdin open": running, "status": status,
                "server left": S.alive(server), "pid file left": bool(s.pid_files())}
    finally:
        s.cleanup()


class ServerTest(unittest.TestCase):
    """I3."""

    def test_debug_server_ends_at_eof(self):
        results = {tool: server_until_eof(tool) for tool in tools()}
        self.assertEqual(results["debug.py"], {"running while stdin open": True, "status": 0,
                                               "server left": False, "pid file left": False})
        if MAKE:
            self.assertEqual(results["make"], results["debug.py"])


def sigterm(tool: str) -> int:
    s = Scenario("openocd-debug", tool)
    try:
        s.wait_for("gdb.pid")
        time.sleep(0.4)
        s.proc.send_signal(signal.SIGTERM)
        time.sleep(0.3)
        s.send("quit\n")
        return s.proc.wait(timeout=30)
    finally:
        s.cleanup()


class SigtermTest(unittest.TestCase):
    """I4."""

    def test_sigterm(self):
        results = {tool: sigterm(tool) for tool in tools()}
        self.assertEqual(results["debug.py"], -signal.SIGTERM)
        if MAKE:
            self.assertEqual(results["make"], results["debug.py"])


if __name__ == "__main__":
    unittest.main()
