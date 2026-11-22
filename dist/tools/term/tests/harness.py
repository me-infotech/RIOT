# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Run the terminal without Make (and live Make) for one case of the sample,
normalised like the golden files."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile

import sample

CLI = os.path.join(sample.TOOL, "term.py")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
TREE = os.path.join(sample.RIOTBASE, "dist", "tools") + os.sep


class Case:
    """A temporary directory with the stubs, HOME and the image directory."""

    def __init__(self, app_dir: str, c: dict):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2b-term-")   # pylint: disable=consider-using-with
        self.app_dir, self.c = app_dir, c
        root = self.tmp.name
        self.home = os.path.join(root, "home")
        os.makedirs(self.home)
        self.bindirbase = os.path.join(root, "bin")
        self.bindir = os.path.join(self.bindirbase, sample.BOARD)
        self.stubs = os.path.join(root, "stubs")
        self.path = sample.stub_path(sample.make_stubs(self.stubs, c["path"]))
        self.term_log = os.path.join(root, "term.log.rec")
        self.tty_log = os.path.join(root, "tty.log")
        self.pairs = [(sample.RIOTBASE, "@RIOTBASE@"), (self.bindir, "@BINDIR@"),
                      (self.bindirbase, "@BINDIRBASE@"), (self.stubs, "@STUBS@"),
                      (self.home, "@HOME@"), (root, "@TMP@")]

    def cleanup(self):
        self.tmp.cleanup()

    def norm(self, text: str) -> str:
        return sample.normalise(text, self.pairs)

    def env(self, **extra) -> dict:
        return sample.environment(self.path, self.home, self.c, self.tmp.name,
                                  G2B_TERM_LOG=self.term_log, G2B_TTY_LOG=self.tty_log, **extra)

    def argv(self, *options) -> list:
        return ([sys.executable, CLI, self.c["goal"], *options, "-C", self.app_dir,
                 f"BOARD={sample.BOARD}", f"BINDIRBASE={self.bindirbase}"]
                + [f"{k}={sample.resolve(v, self.tmp.name)}" for k, v in self.c["vars"].items()])

    def tool(self, *options, **kw):
        return subprocess.run(self.argv(*options), cwd=sample.RIOTBASE, env=self.env(),
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              check=False, **kw)

    def make(self, extra: list):
        argv = sample.make_argv(self.app_dir, self.c, self.bindirbase, self.tmp.name, extra)
        return subprocess.run(argv, cwd=sample.RIOTBASE, env=self.env(), capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, check=False)

    def clear_logs(self):
        for path in (self.term_log, self.tty_log):
            if os.path.exists(path):
                os.remove(path)

    def logs(self) -> list:
        out = []
        for path in (self.term_log, self.tty_log):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as file:
                    text = file.read().rstrip("\n")
                out += [self.norm(line) for line in text.split("\n")] if text else []
        return out

    def dry_run(self) -> tuple:
        res = self.tool("-n")
        return res.returncode, [line for line in self.norm(res.stdout).split("\n") if line], \
            self.norm(res.stderr)

    def terminal_call(self, dry=None) -> tuple:
        """(exit status, lines) in the form of the golden `terminal call`:
        the terminal programs on PATH and the image run (with the
        recorder); for the scripts of dist/tools (which are not replaced in
        the work tree) the call is the command of `-n` with the environment
        of `--print-env`."""
        status, lines, err = dry or self.dry_run()
        if status != 0:
            return status, [f"out: {line}" for line in err.split("\n") if line]
        words = shlex.split(self.norm_back(lines[-1]))
        i = 0
        while i < len(words) and ASSIGNMENT.match(words[i]):
            i += 1
        assign, argv = words[:i], words[i:]
        if "|" in argv:                      # TERMTEE: the terminal is the first command
            argv = argv[:argv.index("|")]
        if argv and argv[0].startswith(TREE):
            return self.reconstructed(lines[-1], assign, argv)
        self.clear_logs()
        sample.fake_image(self.bindir, self.app_dir)
        res = self.tool()
        out = [f"out: {line}" for line in self.norm(res.stdout + res.stderr).split("\n") if line]
        return res.returncode, out + self.logs()

    def norm_back(self, text: str) -> str:
        for path, name in self.pairs:
            text = text.replace(name, path)
        return text

    def reconstructed(self, shown: str, assign: list, argv: list) -> tuple:
        self.clear_logs()
        res = self.tool("--print-env")
        if res.returncode != 0:
            raise AssertionError(res.stderr)
        env = self.env()
        for line in res.stdout.split("\n"):
            if line:
                name, value = line.split("=", 1)
                env[name] = value
        for word in assign:
            name, value = word.split("=", 1)
            env[name] = value
        out = [f"out: {shown}", self.norm("terminal " + argv[0] + "".join(
            f" [{a}]" for a in argv[1:]))]
        out += [self.norm(f"{n}=[{env[n]}]") if n in env else f"{n} unset"
                for n in sample.TERM_READS]
        tty = []
        if os.path.exists(self.tty_log):
            with open(self.tty_log, encoding="utf-8") as file:
                tty = [self.norm(line) for line in file.read().split("\n") if line]
        return 0, out + tty


def sections(app: str) -> dict:
    return sample.read_golden(sample.golden_path(app))[1]


def golden(app: str, name: str, what: str) -> tuple:
    c = sample.CASES[name]
    what = f"make -n {c['goal']}" if what == "dry-run" else what
    return sample.status_and_lines(sections(app)[sample.title(name, sample.APPS[app], c, what)])


def uses_path_or_image(case: Case, dry_lines: list) -> bool:
    """The terminal of a `make -n` output is a program on PATH or the image
    (not a script of dist/tools, which the work tree keeps)."""
    words = shlex.split(case.norm_back(dry_lines[-1]))
    words = [w for w in words if not ASSIGNMENT.match(w)]
    return bool(words) and not words[0].startswith(TREE)
