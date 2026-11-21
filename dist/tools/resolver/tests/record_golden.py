#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record golden/boards-supported.txt: `make info-boards-supported` for the
applications of the sample, with the boards of the sample in the
environment (BOARDS on Make's command line would be passed on to every
sub-make and list each board twice).

The other golden files of the resolver are those of step G0-1
(dist/tools/config_data/tests/golden). Record on an unchanged tree of the
base commit, never in the working tree (Make writes bin/ files):

  git archive <base> | tar -x -C /tmp/base
  record_golden.py --root /tmp/base --commit <base>
"""

import argparse
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "config_data", "tests"))

# pylint: disable=wrong-import-position
import record_golden as g01  # noqa: E402
import sample  # noqa: E402

GOLDEN = os.path.join(HERE, "golden", "boards-supported.txt")
TARGET = "info-boards-supported"


def argv(app_dir: str) -> list:
    return ["make", "--no-print-directory", "-C", app_dir, TARGET]


def command(app_dir: str) -> str:
    """The key of the entry: environment and command."""
    return f"BOARDS='{' '.join(sample.BOARDS)}' " + " ".join(argv(app_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = os.path.abspath(args.root)
    lines = ["# golden output of GNU Make for the parity tests of step G0-2",
             "# generator: dist/tools/resolver/tests/record_golden.py",
             f"# commit: {args.commit} (git archive)",
             f"# date: {datetime.date.today().isoformat()}",
             f"# make: {g01.first_line(['make', '--version'])}",
             "# environment: env -i PATH HOME LC_ALL=C BOARDS; stdout and stderr merged"]
    for app_dir in sample.APPS.values():
        env = {**sample.environment(), "BOARDS": " ".join(sample.BOARDS)}
        res = subprocess.run(argv(app_dir), cwd=root, env=env, check=False, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines += ["## " + command(app_dir), f"## exit: {res.returncode}"]
        lines += sample.normalize(res.stdout, root).splitlines()
    with open(GOLDEN, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    print(f"wrote {os.path.relpath(GOLDEN, sample.RIOTBASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
