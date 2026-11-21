# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Run the flash without Make (and live Make) for one case of the sample,
normalised like the golden files."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile

import sample

CLI = os.path.join(sample.TOOL, "flash.py")


class Case:
    """A temporary directory with the stub tools and the image directory."""

    def __init__(self, app_dir: str, variables: dict, jlink_found: bool):
        self.tmp = tempfile.TemporaryDirectory(prefix="g3-flash-")
        self.app_dir, self.variables = app_dir, variables
        self.bindirbase = os.path.join(self.tmp.name, "bin")
        self.bindir = os.path.join(self.bindirbase, sample.BOARD)
        self.stubs = sample.make_stubs(os.path.join(self.tmp.name, "stubs"))
        self.path = sample.stub_path(self.stubs, jlink_found)
        self.stub_log = os.path.join(self.tmp.name, "stub.log")
        self.pairs = [(sample.RIOTBASE, "@RIOTBASE@"), (self.bindir, "@BINDIR@"),
                      (self.bindirbase, "@BINDIRBASE@"),
                      (os.path.join(self.tmp.name, "stubs"), "@STUBS@")]

    def cleanup(self):
        self.tmp.cleanup()

    def norm(self, text: str) -> str:
        return sample.normalise(text, self.pairs)

    def tool(self, *options, extra_env=None, path=None):
        argv = [sys.executable, CLI, "flash", *options, "-C", self.app_dir,
                f"BOARD={sample.BOARD}", "-B", self.bindir] + \
            [f"{k}={v}" for k, v in self.variables.items()]
        env = sample.environment(path or self.path, **(extra_env or {}))
        return subprocess.run(argv, cwd=sample.RIOTBASE, env=env, capture_output=True,
                              text=True, check=False)

    def make(self, extra: list, extra_env=None):
        argv = sample.make_argv(self.app_dir, self.variables, self.bindirbase, extra)
        env = sample.environment(self.path, **(extra_env or {}))
        return subprocess.run(argv, cwd=sample.RIOTBASE, env=env, capture_output=True,
                              text=True, check=False)

    def stub_calls(self) -> list:
        if not os.path.exists(self.stub_log):
            return []
        with open(self.stub_log, encoding="utf-8") as file:
            return self.norm(file.read().rstrip("\n")).split("\n")

    def dry_run(self) -> tuple:
        res = self.tool("-n")
        return res.returncode, [line for line in self.norm(res.stdout).split("\n") if line]

    def environment(self) -> list:
        """The golden form of the flasher environment: env -i PATH HOME
        LC_ALL plus what the flash without Make exports."""
        res = self.tool("--print-env")
        if res.returncode != 0:
            raise AssertionError(res.stderr)
        env = sample.environment(self.path)
        for line in res.stdout.split("\n"):
            if line:
                name, value = line.split("=", 1)
                env[name] = value
        return [self.norm(f"{n}=[{env[n]}]") if n in env else f"{n} unset"
                for n in sample.ENV_NAMES]

    def stub_run(self, tool=True) -> tuple:
        sample.fake_image(self.bindir, self.app_dir)
        if tool:
            res = self.tool("--no-build", extra_env={"G3_STUB_LOG": self.stub_log})
        else:
            res = self.make(["-o", "all", "flash"], {"G3_STUB_LOG": self.stub_log})
        return res, self.stub_calls()


def argv_of(line: str) -> list:
    """A command line as argument vector (blanks of empty variables do not count)."""
    return shlex.split(line)


def sections(app: str) -> dict:
    return sample.read_golden(sample.golden_path(app))[1]


def golden(app: str, case: str, variables: dict, what: str) -> list:
    return sections(app)[sample.title(case, sample.APPS[app], variables, what)]
