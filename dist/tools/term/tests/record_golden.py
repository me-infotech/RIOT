#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G2B-1 from GNU Make (see sample.py).

Run on an unchanged tree of the base commit, one Make at a time:

  git archive <base> | tar -x -C /tmp/base
  record_golden.py --root /tmp/base --commit <base>

The tree is changed only while the terminal calls are recorded: the terminal
scripts of dist/tools are replaced by the recorder and restored afterwards.
No board is needed: stubs stand for the terminals, `date` and ttys.py.
TMPDIR points into a temporary directory, so nothing Make creates with
mktemp stays behind.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample  # noqa: E402  pylint: disable=wrong-import-position


def first_line(argv: list) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "not installed"
    return (res.stdout.splitlines() or ["not installed"])[0]


def header(commit: str) -> list:
    return [
        "# golden output of GNU Make for the parity tests of step G2B-1 (terminal without Make)",
        "# generator: dist/tools/term/tests/record_golden.py",
        f"# commit: {commit} (git archive; terminal scripts replaced only for the calls)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        f"# stubs: date -> {sample.DATE}, ttys.py -> '{sample.TTY_ANSWER}' or failure, "
        f"terminals -> recorder; USER={sample.USER}",
        "# environment: env -i PATH HOME LC_ALL=C USER TMPDIR (PATH: stub directories first);",
        "#   stdout and stderr merged, `make: ***` lines of the terminal call left out;",
        "#   stdin /dev/null; BINDIRBASE outside the tree",
        f"# terminal environment: {' '.join(sample.TERM_READS)}",
    ]


class Recorders:
    """The terminal scripts of the tree replaced by the recorder, restored on exit."""

    def __init__(self, root: str, keep: str):
        self.root, self.keep = root, keep

    def __enter__(self):
        for rel in sample.TREE_TERMINALS:
            path = os.path.join(self.root, rel)
            shutil.copy2(path, os.path.join(self.keep, rel.replace("/", "_")))
            sample.write_executable(path, sample.recorder())
        return self

    def __exit__(self, *exc):
        for rel in sample.TREE_TERMINALS:
            shutil.copy2(os.path.join(self.keep, rel.replace("/", "_")),
                         os.path.join(self.root, rel))


def read(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as file:
        text = file.read().rstrip("\n")
    return text.split("\n") if text else []


class Run:
    """The temporary directory of one case."""

    def __init__(self, root: str, app_dir: str, c: dict, tmp: str):
        self.root, self.app_dir, self.c, self.tmp = root, app_dir, c, tmp
        self.home = os.path.join(tmp, "home")
        os.makedirs(self.home, exist_ok=True)
        self.bindirbase = os.path.join(tmp, "bin")
        self.bindir = os.path.join(self.bindirbase, sample.BOARD)
        self.stubs = os.path.join(tmp, "stubs")
        self.path = sample.stub_path(sample.make_stubs(self.stubs, c["path"]))
        self.term_log = os.path.join(tmp, "term.log.rec")
        self.tty_log = os.path.join(tmp, "tty.log")
        self.pairs = [(root, "@RIOTBASE@"), (self.bindir, "@BINDIR@"),
                      (self.bindirbase, "@BINDIRBASE@"), (self.stubs, "@STUBS@"),
                      (self.home, "@HOME@"), (tmp, "@TMP@")]

    def norm(self, text: str) -> str:
        return sample.normalise(text, self.pairs)

    def make(self, extra: list) -> tuple:
        argv = sample.make_argv(self.app_dir, self.c, self.bindirbase, self.tmp, extra)
        env = sample.environment(self.path, self.home, self.c, self.tmp,
                                 G2B_TERM_LOG=self.term_log, G2B_TTY_LOG=self.tty_log)
        res = subprocess.run(argv, cwd=self.root, env=env, capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, check=False)
        return res.returncode, (res.stdout + res.stderr).rstrip("\n")


def record_case(root, name, app_dir, c, tmp) -> list:
    run = Run(root, app_dir, c, tmp)
    goal = c["goal"]
    status, text = run.make(["-n", goal])
    out = [sample.title(name, app_dir, c, f"make -n {goal}"), f"## exit: {status}",
           run.norm(text)]
    for path in (run.term_log, run.tty_log):
        if os.path.exists(path):
            os.remove(path)
    sample.fake_image(run.bindir, app_dir)
    status, text = run.make([goal])
    lines = [f"out: {line}" for line in run.norm(text).split("\n")
             if line and not line.startswith("make: ***")]
    out += [sample.title(name, app_dir, c, "terminal call"), f"## exit: {status}"]
    out += lines + [run.norm(line) for line in read(run.term_log) + read(run.tty_log)]
    return out


def record(root: str, commit: str) -> None:
    os.makedirs(sample.GOLDEN, exist_ok=True)
    with tempfile.TemporaryDirectory() as keep, Recorders(root, keep):
        for app, app_dir in sample.APPS.items():
            lines = header(commit)
            for name, c in sample.cases(app).items():
                with tempfile.TemporaryDirectory(prefix="g2b-term-") as tmp:
                    lines += record_case(root, name, app_dir, c, tmp)
            with open(sample.golden_path(app), "w", encoding="utf-8") as file:
                file.write("\n".join(lines + ["## end"]) + "\n")
            print(f"wrote {os.path.relpath(sample.golden_path(app), sample.RIOTBASE)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    record(os.path.abspath(args.root), args.commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
