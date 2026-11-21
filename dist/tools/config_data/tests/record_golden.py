#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of the parity tests from GNU Make.

Runs Make once per application, board and target of sample.py, one Make at
a time, and writes golden/<app>__<board>.txt. Each file starts with a header
(generator, commit, date, Make version, host compiler); each entry with
`## make …` (the command) and `## exit: N`, followed by Make's output.

The golden files of step G0-1 were recorded on the base commit, before any
dependency or feature file was converted. Re-record only for a reviewed
change of Make's behaviour and review the diff.

Adding targets later (step G0-2 added sample.CPU_TARGETS): run Make on an
unchanged tree of the base commit and insert only the new entries, keeping
every recorded entry and the header:

  git archive <base> | tar -x -C /tmp/base
  record_golden.py --root /tmp/base --commit <base> --add info-cpu …
"""

import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample  # noqa: E402  pylint: disable=wrong-import-position


def first_line(argv: list) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "not installed"
    return (res.stdout.splitlines() or ["not installed"])[0]


def header() -> list:
    commit = subprocess.run(["git", "-C", sample.RIOTBASE, "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", sample.RIOTBASE, "status", "--porcelain", "--",
                            "Makefile*", "makefiles", "boards", "cpu", "sys", "drivers",
                            "pkg", "examples"],
                           capture_output=True, text=True, check=True).stdout.strip()
    return [
        "# golden output of GNU Make for the parity tests of step G0-1",
        "# generator: dist/tools/config_data/tests/record_golden.py",
        f"# commit: {commit}" + (" (make files modified!)" if dirty else ""),
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        f"# host-gcc: {first_line(['gcc', '--version'])}",
        f"# arm-none-eabi-gcc: {first_line(['arm-none-eabi-gcc', '--version'])}",
        "# environment: env -i PATH HOME LC_ALL=C; stdout and stderr merged",
    ]


def add_targets(root: str, commit: str, new: list) -> int:
    """Insert the entries of `new` into the existing golden files, recorded
    in the tree `root` (an unchanged checkout of `commit`)."""
    stamp = (f"# added {datetime.date.today().isoformat()}: {' '.join(new)}; "
             f"recorded on {commit} (git archive), {first_line(['make', '--version'])}")
    for app, app_dir, board in sample.pairs():
        path = sample.golden_path(app, board)
        head, entries = sample.read_golden(path)
        lines = list(head) + ([stamp] if stamp not in head else [])
        for target in sample.targets(app):
            argv = sample.make_argv(app_dir, board, target)
            key = " ".join(argv)
            if target in new:
                entries[key] = sample.run_make(argv, root)
            status, output = entries[key]
            lines += ["## " + key, f"## exit: {status}"] + output
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines + ["## end"]) + "\n")
        print(f"updated {os.path.relpath(path, sample.RIOTBASE)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="tree to run Make in (with --add)")
    parser.add_argument("--commit", help="commit of that tree (with --add)")
    parser.add_argument("--add", nargs="+", metavar="TARGET",
                        help="record only these targets and insert them")
    args = parser.parse_args()
    if args.add:
        if not (args.root and args.commit):
            parser.error("--add needs --root and --commit")
        return add_targets(os.path.abspath(args.root), args.commit, args.add)
    head = header()
    os.makedirs(sample.GOLDEN, exist_ok=True)
    for app, app_dir, board in sample.pairs():
        lines = list(head)
        for target in sample.targets(app):
            argv = sample.make_argv(app_dir, board, target)
            status, output = sample.run_make(argv)
            lines += ["## " + " ".join(argv), f"## exit: {status}"] + output
        path = sample.golden_path(app, board)
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines + ["## end"]) + "\n")
        print(f"wrote {os.path.relpath(path, sample.RIOTBASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
