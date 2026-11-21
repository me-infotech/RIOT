#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G3-1 from GNU Make (see sample.py).

Run once on an unchanged tree of the base commit, one Make at a time:

  git archive <base> | tar -x -C /tmp/base
  record_golden.py --root /tmp/base --commit <base> --pkg-cache <dir>

--pkg-cache: a BUILD_DIR whose packages Make has prepared before (e.g.
`make -C examples/networking/gnrc/networking BOARD=nrf52840dk
fetch_nrfx_vendor_headers pkg-prepare BUILD_DIR=<dir>`); it is copied, never
changed. Without arm-none-eabi-gcc Make prints the commands with the
toolchain probes failing; the header records the versions found.
"""

import argparse
import datetime
import hashlib
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


def normalise(text: str, root: str, build_dir: str, bindirbase: str) -> str:
    bindir = os.path.join(bindirbase, sample.BOARD)
    for path, name in ((bindir, "@BINDIR@"), (bindirbase, "@BINDIRBASE@"),
                       (build_dir, "@BUILD_DIR@"), (root, "@RIOTBASE@")):
        text = text.replace(path, name)
    return text


def run_make(root: str, app_dir: str, extra: list) -> tuple:
    argv = sample.make_argv(app_dir, extra)
    res = subprocess.run(argv, cwd=root, env=sample.environment(), capture_output=True,
                         text=True, check=False)
    return argv, res.returncode, (res.stdout + res.stderr).rstrip("\n")


def record(root: str, commit: str, cache: str) -> None:
    head = [
        "# golden output of GNU Make for the parity tests of step G3-1 (build without Make)",
        "# generator: dist/tools/cmake_gen/tests/record_golden.py",
        f"# commit: {commit} (git archive, unchanged)",
        f"# date: {datetime.date.today().isoformat()}",
        f"# make: {first_line(['make', '--version'])}",
        f"# arm-none-eabi-gcc: {first_line(['arm-none-eabi-gcc', '--version'])}",
        f"# host-gcc: {first_line(['gcc', '--version'])}",
        f"# git: {first_line(['git', '--version'])}",
        "# environment: env -i PATH HOME LC_ALL=C; stdout and stderr merged;",
        "#   BUILD_DIR and BINDIRBASE outside the tree (shown as @BUILD_DIR@, @BINDIRBASE@)",
    ]
    os.makedirs(sample.GOLDEN, exist_ok=True)
    for app, app_dir in sample.APPS.items():
        lines = list(head)
        with tempfile.TemporaryDirectory() as tmp:
            fresh, prepared = os.path.join(tmp, "fresh"), os.path.join(tmp, "prepared")
            bindirbase = os.path.join(tmp, "bin")
            os.makedirs(fresh)
            shutil.copytree(cache, prepared, symlinks=True)
            dirs = [f"BINDIRBASE={bindirbase}"]
            bindir = os.path.join(bindirbase, sample.BOARD)
            argv, status, out = run_make(root, app_dir, [f"BUILD_DIR={fresh}", *dirs, "-n", "-k"])
            lines += [f"## {' '.join(sample.make_argv(app_dir))} BUILD_DIR=@BUILD_DIR@ "
                      f"BINDIRBASE=@BINDIRBASE@ -n -k {sample.FRESH}", f"## exit: {status}",
                      normalise(out, root, fresh, bindirbase)]
            header = os.path.join(bindir, "riotbuild", "riotbuild.h")
            run_make(root, app_dir, [f"BUILD_DIR={prepared}", *dirs, header])
            argv, status, out = run_make(root, app_dir,
                                         [f"BUILD_DIR={prepared}", *dirs, "-n", "-k"])
            lines += [f"## {' '.join(sample.make_argv(app_dir))} BUILD_DIR=@BUILD_DIR@ "
                      f"BINDIRBASE=@BINDIRBASE@ -n -k {sample.PREPARED}", f"## exit: {status}",
                      normalise(out, root, prepared, bindirbase)]
            pp_header = os.path.join(bindir, "preprocessor", "preprocessor_successor.h")
            run_make(root, app_dir, [f"BUILD_DIR={prepared}", *dirs, pp_header])
            with open(header, encoding="utf-8") as file:
                lines += [sample.RIOTBUILD_H, normalise(file.read().rstrip("\n"), root,
                                                        prepared, bindirbase)]
            with open(pp_header, "rb") as file:
                data = file.read()
            count = data.count(b"\n")
            lines += [sample.PP_H, f"sha256 {hashlib.sha256(data).hexdigest()}",
                      f"lines {count}"]
        with open(sample.golden_path(app), "w", encoding="utf-8") as file:
            file.write("\n".join(lines + ["## end"]) + "\n")
        print(f"wrote {os.path.relpath(sample.golden_path(app), sample.RIOTBASE)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--pkg-cache", required=True)
    args = parser.parse_args()
    record(os.path.abspath(args.root), args.commit, os.path.abspath(args.pkg_cache))
    return 0


if __name__ == "__main__":
    sys.exit(main())
