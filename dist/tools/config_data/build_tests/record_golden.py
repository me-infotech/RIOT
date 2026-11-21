#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Record the golden files of step G0-3: Make's expanded value of every
variable the build data writes and the environment Make exports, for the
applications of the scope on nrf52840dk, in a checkout of the Make files
before the split (the build part still written in Make).

  record_golden.py ROOT     ROOT: a checkout of scope.yaml build_base (or a
                            commit with the same Make files), e.g. a clone in
                            a temporary directory

The variable names come from the build data of this tree; they are written
to the golden file, so the test compares exactly these names.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402  pylint: disable=wrong-import-position


def names() -> tuple:
    rules = C.all_rules()
    return (sorted(C.written_variables(rules) - set(C.VERSION_VARS)),
            sorted(C.exported_variables(rules)))


def header(root: str) -> list:
    commit = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                            text=True, check=False).stdout.strip()
    make = subprocess.run(["make", "--version"], capture_output=True, text=True,
                          check=False).stdout.split("\n")[0]
    return [f"# commit: {commit}", f"# make: {make}",
            "# command: make -C <app> BOARD=nrf52840dk -f Makefile -f build_tests/dump.mk "
            "G003_NAMES=<names> riot-g003-env",
            "# paths: @RIOTBASE@; RIOT_VERSION and the git description masked"]


def main(argv) -> int:
    root = os.path.abspath(argv[1])
    variables, exported = names()
    os.makedirs(C.GOLDEN, exist_ok=True)
    for app, app_dir in C.APPS.items():
        lines = header(root) + C.make_values(root, app_dir, variables, exported) + ["## end"]
        target = os.path.join(C.GOLDEN, f"{app}__{C.BOARD}.txt")
        with open(target, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        print(f"{os.path.relpath(target, C.RIOTBASE)}: {len(lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
