#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G2B-3 from GNU Make (see tsample.py).

Run on an unchanged tree of the base commit:

  git archive <base> | tar -x -C <dir>
  record_golden.py --root <dir> --commit <base>

The tree is not changed: nothing is built (TEST_DEPS is empty on
nrf52840dk), the scripts are the recorder in a temporary directory.
"""

import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsample as S  # noqa: E402  pylint: disable=wrong-import-position


def header(commit: str) -> list:
    make = subprocess.run(["make", "--version"], capture_output=True, text=True,
                          check=False).stdout.splitlines()[0]
    return [
        "# golden output of GNU Make for the parity tests of step G2B-3 (tests without Make)",
        "# generator: dist/tools/test/tests/record_golden.py",
        f"# commit: {commit} (git archive, unchanged)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {make}",
        "# call: make -C <app> [-n] <goal> BOARD=nrf52840dk [VAR=VALUE…]; stubs: git fails;",
        "#   scripts: the recorder @REC@; environment: env -i PATH HOME LC_ALL=C USER TMPDIR",
        "#   G2B_*; stdout and stderr merged, `make: ***` and directory lines left out",
        f"# script environment: {' '.join(S.TEST_READS)}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    os.makedirs(S.GOLDEN, exist_ok=True)
    for app in S.APPS:
        lines = header(args.commit) + S.record_app(os.path.abspath(args.root), app)
        with open(S.golden_path(app), "w", encoding="utf-8") as file:
            file.write("\n".join(lines + ["## end"]) + "\n")
        print(f"wrote {os.path.relpath(S.golden_path(app), S.RIOTBASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
