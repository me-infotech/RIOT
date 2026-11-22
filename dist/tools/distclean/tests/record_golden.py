#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden file of step G2C-2 from GNU Make (see dsample.py).

Run on an unchanged checkout of the base commit, one Make at a time:

  git clone -q --shared --no-checkout <repository> /tmp/base
  git -C /tmp/base checkout -q <base>
  record_golden.py --root /tmp/base --commit <base>

The tree is not changed: Make runs on copies of the applications outside it
(RIOTBASE and BUILD_DIR on the command line), with a stub toolchain and
stand-in prepared packages (no toolchain, no network).
"""

import argparse
import datetime
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402


def first_line(argv: list) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "not installed"
    return (res.stdout.splitlines() or ["not installed"])[0]


def header(commit: str) -> list:
    return [
        "# golden output of GNU Make for the parity tests of step G2C-2 "
        "(distclean without Make)",
        "# generator: dist/tools/distclean/tests/record_golden.py",
        f"# commit: {commit} (git checkout, unchanged; the applications copied outside it)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        "# environment: env -i PATH HOME LC_ALL=C GIT_ALLOW_PROTOCOL=file; umask 022; "
        "stdout, then stderr",
        "# tree cases: make -j1 <goal> with a stub toolchain and stand-in prepared packages "
        "in BUILD_DIR=@TMP@/build (dist/tools/clean/tests/sample.py), then the stand-ins "
        "sample.EXTRA and dsample.KEEP_IN_BUILD_DIR (-locked: dsample.LOCKED, mode 0555), "
        "then make distclean",
    ]


def record(root: str, commit: str) -> None:
    os.makedirs(D.GOLDEN, exist_ok=True)
    lines = header(commit)
    for case in D.CASES:
        with tempfile.TemporaryDirectory(prefix="g2c-distclean-golden-") as tmp:
            status, out = D.dry_case(case, tmp, make_root=root)
        lines += [D.dry_title(case), f"## exit: {status}"] + out
    for tree in D.TREES:
        with tempfile.TemporaryDirectory(prefix="g2c-distclean-golden-") as tmp:
            lines += D.make_build_and_distclean(tree, tmp, root)
    with open(D.golden_path(), "w", encoding="utf-8") as file:
        file.write("\n".join(lines + ["## end"]) + "\n")
    print(f"wrote {os.path.relpath(D.golden_path(), D.RIOTBASE)}")


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
