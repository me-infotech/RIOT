#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G3-2 from GNU Make (see sample.py).

Run on an unchanged tree of the base commit, one Make at a time:

  git archive <base> | tar -x -C /tmp/base
  record_golden.py --root /tmp/base --commit <base>

The tree is changed only while the environment is recorded: the flasher
scripts are replaced by a recorder and restored afterwards. No board is
needed: the stub tools (sample.STUB) stand for JLinkExe, openocd and pipx.
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
        "# golden output of GNU Make for the parity tests of step G3-2 (flash without Make)",
        "# generator: dist/tools/flash/tests/record_golden.py",
        f"# commit: {commit} (git archive; flasher scripts replaced only for the environment)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        f"# JLinkExe, openocd, pipx: stubs (sample.STUB); real ones: "
        f"{'none' if not any(shutil.which(t) for t in sample.STUB_TOOLS) else 'present'}",
        "# environment: env -i PATH HOME LC_ALL=C (PATH: stub directories first);",
        "#   stdout and stderr merged; BINDIRBASE outside the tree",
        f"# flasher environment: {' '.join(sample.ENV_NAMES)}",
    ]


class Recorders:
    """The flasher scripts of the tree replaced by the recorder, restored on exit."""

    def __init__(self, root: str, keep: str):
        self.root, self.keep = root, keep

    def __enter__(self):
        for rel in sample.FLASHER_READS:
            path = os.path.join(self.root, rel)
            shutil.copy2(path, os.path.join(self.keep, rel.replace("/", "_")))
            sample.write_executable(path, sample.RECORDER.format(
                name=rel, names=sample.ENV_NAMES))
        return self

    def __exit__(self, *exc):
        for rel in sample.FLASHER_READS:
            shutil.copy2(os.path.join(self.keep, rel.replace("/", "_")),
                         os.path.join(self.root, rel))


def run(root, app_dir, variables, bindirbase, extra, env):
    argv = sample.make_argv(app_dir, variables, bindirbase, extra)
    res = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False)
    return res.returncode, (res.stdout + res.stderr).rstrip("\n")


def read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as file:
        return file.read().rstrip("\n")


def record_case(root, app, app_dir, case, variables, jlink_found, tmp) -> list:
    bindirbase = os.path.join(tmp, "bin")
    bindir = os.path.join(bindirbase, sample.BOARD)
    dirs = sample.make_stubs(os.path.join(tmp, "stubs"))
    path = sample.stub_path(dirs, jlink_found)
    pairs = [(root, "@RIOTBASE@"), (bindir, "@BINDIR@"), (bindirbase, "@BINDIRBASE@"),
             (os.path.join(tmp, "stubs"), "@STUBS@")]
    out = []
    status, text = run(root, app_dir, variables, bindirbase, ["-n", "-o", "all", "flash"],
                       sample.environment(path))
    out += [sample.title(case, app_dir, variables, "make -n -o all flash"),
            f"## exit: {status}", sample.normalise(text, pairs)]
    sample.fake_image(bindir, app_dir)
    env_log = os.path.join(tmp, "env.log")
    keep = os.path.join(tmp, "keep")
    os.makedirs(keep, exist_ok=True)
    with Recorders(root, keep):
        status, text = run(root, app_dir, variables, bindirbase, ["-o", "all", "flash"],
                           sample.environment(path, G3_ENV_LOG=env_log))
    out += [sample.title(case, app_dir, variables, "flasher environment"),
            f"## exit: {status}", sample.normalise(read(env_log), pairs)]
    stub_log = os.path.join(tmp, "stub.log")
    status, text = run(root, app_dir, variables, bindirbase, ["-o", "all", "flash"],
                       sample.environment(path, G3_STUB_LOG=stub_log))
    out += [sample.title(case, app_dir, variables, "stub calls"),
            f"## exit: {status}", sample.normalise(read(stub_log), pairs)]
    return out


def record(root: str, commit: str) -> None:
    os.makedirs(sample.GOLDEN, exist_ok=True)
    for app, app_dir in sample.APPS.items():
        lines = header(commit)
        for case, (variables, jlink_found) in sample.cases(app).items():
            with tempfile.TemporaryDirectory() as tmp:
                lines += record_case(root, app, app_dir, case, variables, jlink_found, tmp)
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
