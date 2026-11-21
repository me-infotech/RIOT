#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden file of step G3-3 from GNU Make (see sample.py).

Run on an unchanged checkout of the base commit (a git checkout: the recipe
runs `git describe`), one Make at a time:

  git clone -q --shared --no-checkout <repository> /tmp/base
  git -C /tmp/base checkout -q <base>
  record_golden.py --root /tmp/base --commit <base>

The tree is not changed: Make runs on a copy of the application outside it
(RIOTBASE on the command line), with stand-in build products (no toolchain).
"""

import argparse
import datetime
import os
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
        "# golden output of GNU Make for the parity tests of step G3-3 (bindist without Make)",
        "# generator: dist/tools/bindist/tests/record_golden.py",
        f"# commit: {commit} (git checkout, unchanged; the application copied outside it)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        f"# cp: {first_line(['cp', '--version'])}",
        "# environment: env -i PATH HOME LC_ALL=C; umask 022; stdout, then stderr",
        f"# sources: mode 0644/0755, mtime {sample.FIXED}; stand-in build products "
        "(objects, ELF, binary of the build plan)",
        "# masked: RIOT_VERSION computed from git (not when set on the command line), "
        "git describe",
    ]


def record(root: str, commit: str) -> None:
    os.makedirs(sample.GOLDEN, exist_ok=True)
    lines = header(commit)
    for case in sample.CASES:
        with tempfile.TemporaryDirectory(prefix="g3-bindist-golden-") as tmp:
            lines += sample.run_case(case, tmp, make_root=root)
    with open(sample.golden_path(), "w", encoding="utf-8") as file:
        file.write("\n".join(lines + ["## end"]) + "\n")
    print(f"wrote {os.path.relpath(sample.golden_path(), sample.RIOTBASE)}")


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
