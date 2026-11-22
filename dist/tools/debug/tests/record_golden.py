#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G2B-2 from GNU Make (see debug_sample.py).

Run on an unchanged tree of the base commit, one Make at a time:

  git archive <base> | tar -x -C <dir>
  record_golden.py --root <dir> --commit <base>

The tree is not changed: the scripts of dist/tools run, the stub tools on
PATH stand for the probe, the GDB servers and GDB. TMPDIR points into a
temporary directory, so nothing Make or the scripts create with mktemp stays
behind; every server stub is ended after its case.
"""

import argparse
import datetime
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import debug_sample as S  # noqa: E402  pylint: disable=wrong-import-position


def first_line(argv: list) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "not installed"
    return (res.stdout.splitlines() or ["not installed"])[0]


def header(commit: str) -> list:
    return [
        "# golden output of GNU Make for the parity tests of step G2B-2 (debugger without Make)",
        "# generator: dist/tools/debug/tests/record_golden.py",
        f"# commit: {commit} (git archive, unchanged)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        "# stubs: openocd, JLinkGDBServer (servers), arm-none-eabi-gdb or gdb-multiarch, "
        "JLinkExe (DLL version V7.94), pipx, setsid (then the real one); "
        f"ttys.py -> '{S.TS.TTY_ANSWER}'; USER={S.TS.USER}",
        "# environment: env -i PATH HOME LC_ALL=C USER TMPDIR G2B_* (PATH: stub directories "
        "first);",
        "#   stdout and stderr merged, `make: ***` lines left out; stdin a pipe closed once "
        "the server started;",
        "#   BINDIRBASE outside the tree; `left running`: server stubs alive 0.3 s after the call",
        f"# debugger environment: {' '.join(S.DEBUG_READS)}",
    ]


def record_case(root, name, app_dir, c, tmp) -> list:
    run = S.Run(root, app_dir, c, tmp)
    goal = c["goal"]
    status, out, err = run.capture(run.make_argv(["-n", goal]))
    out = [S.title(name, app_dir, c, f"make -n {goal}"), f"## exit: {status}",
           run.norm((out + err).rstrip("\n"))]
    if c["outside"] or c["error"]:
        return out
    status, lines, stubs = run.run(run.make_argv([goal]))
    return out + [S.title(name, app_dir, c, "run"), f"## exit: {status}"] + lines + stubs


def record(root: str, commit: str) -> None:
    os.makedirs(S.GOLDEN, exist_ok=True)
    for app, app_dir in S.APPS.items():
        lines = header(commit)
        for name, c in S.cases(app).items():
            if not c["record"]:
                continue
            with tempfile.TemporaryDirectory(prefix="g2b-debug-") as tmp:
                lines += record_case(root, name, app_dir, c, tmp)
        with open(S.golden_path(app), "w", encoding="utf-8") as file:
            file.write("\n".join(lines + ["## end"]) + "\n")
        print(f"wrote {os.path.relpath(S.golden_path(app), S.RIOTBASE)}")


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
