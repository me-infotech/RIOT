# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""The parity sample of step G0-1: applications, boards and Make targets.

The dependency and feature files converted to YAML are exactly those GNU
Make reads for these applications and boards (scope.yaml). The golden files
in golden/ hold Make's output for them, recorded before the conversion; the
parity tests run Make again and compare.
"""

import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLDEN = os.path.join(HERE, "golden")

APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
BOARDS = ["nrf52840dk", "native64"]

# Make targets compared for every application and board. MAKEFILE_LIST shows
# that Make reads the same files in the same order.
INFO_TARGETS = ["info-modules", "info-packages", "info-features-used",
                "info-features-missing", "info-features-provided",
                "info-debug-variable-MAKEFILE_LIST"]
# Added in step G0-2 (resolver): the CPU of the board and its data. Recorded
# on the same base commit (record_golden.py --root/--add, see there).
CPU_TARGETS = ["info-cpu", "info-debug-variable-CPU_MODEL", "info-debug-variable-CPU_CORE",
               "info-debug-variable-CPU_FAM", "info-debug-variable-CPU_ARCH"]
INFO_TARGETS += CPU_TARGETS
# The build command list (`make -n -k`) is compared for these applications.
# No toolchain is needed: Make prints the commands and stops where a
# generated file is missing, at the same place each time.
BUILD_LIST_APPS = ["hello-world"]
BUILD_LIST = "build-command-list"

PLACEHOLDER = "@RIOTBASE@"


def environment() -> dict:
    """Nothing but PATH, HOME and the C locale, so the shell environment of
    the caller cannot change Make's result."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}


def make_argv(app_dir: str, board: str, target: str) -> list:
    argv = ["make", "--no-print-directory", "-C", app_dir, f"BOARD={board}"]
    if target == BUILD_LIST:
        return argv + ["-n", "-k"]
    return argv + [target]


def pairs():
    """(application name, directory, board) of the sample."""
    return [(app, app_dir, board) for app, app_dir in APPS.items() for board in BOARDS]


def targets(app: str) -> list:
    return INFO_TARGETS + ([BUILD_LIST] if app in BUILD_LIST_APPS else [])


def normalize(text: str, root: str = RIOTBASE) -> str:
    """Replace the repository path, so golden files are portable."""
    return text.replace(root, PLACEHOLDER)


VERSION_RE = re.compile(r'-DRIOT_VERSION=\\"[^\\"]*\\"')


def mask_version(result: tuple) -> tuple:
    """(status, lines) with RIOT_VERSION masked: `git describe` names the
    commit and branch of the checkout (the golden files were recorded on
    another branch), not a result of the build configuration."""
    status, lines = result
    return status, [VERSION_RE.sub('-DRIOT_VERSION=\\"@VERSION@\\"', line) for line in lines]


# Step G0-3: the build part of the board, CPU, build system and package Make
# files is generated from the build data into include files (scope.yaml
# `build`, adapter `part`) and makefiles/build_providers.inc.mk defines the
# probes; Make reads these files in addition, and the Make files they were
# taken from got shorter. Both are masked when the golden files (recorded
# before) are compared: the generated files are dropped from MAKEFILE_LIST
# and the line numbers in Make's messages about the split Make files.
G003_SPLIT = ("Makefile.include", "pkg.mk", "Makefile.nrfx", "cflags.inc.mk", "newlib.mk",
              "gnu.inc.mk", "cortexm.inc.mk", "bindist.inc.mk", "Makefile")
LINE_RE = re.compile(r"((?:^|[\s/])(?:" + "|".join(re.escape(n) for n in G003_SPLIT)
                     + r")):[0-9]+:")


def g003_generated() -> tuple:
    """The include files generated from build data and the providers file
    (paths relative to the repository root)."""
    import yaml  # pylint: disable=import-outside-toplevel
    with open(os.path.join(RIOTBASE, "dist", "tools", "config_data", "scope.yaml"),
              encoding="utf-8") as file:
        build = yaml.safe_load(file).get("build") or {}
    parts = [data[:-len(".yaml")] + ".mk" for data, entry in build.items()
             if entry["adapter"] == "part"]
    return tuple(sorted(parts + ["makefiles/build_providers.inc.mk"]))


def mask_g003(result: tuple) -> tuple:
    """(status, lines) without the G0-3 adapters in MAKEFILE_LIST and with
    the line numbers of messages about the split Make files masked."""
    status, lines = result
    generated = g003_generated()
    out = []
    for line in lines:
        words = line.split(" ")
        if any(os.path.normpath(w).endswith(generated) for w in words if w.endswith(".mk")):
            words = [w for w in words if not (w.endswith(".mk") and any(
                os.path.normpath(w) == g or os.path.normpath(w).endswith("/" + g)
                for g in generated))]
            line = " ".join(words)
        out.append(LINE_RE.sub(r"\1:@LINE@:", line))
    return status, out


def golden_path(app: str, board: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{board}.txt")


def read_golden(path: str) -> tuple:
    """(header lines, {command: (exit status, output lines)}).

    The file ends with the line "## end", so that an empty last output line
    does not leave a blank line at the end of the file."""
    header, entries, command = [], {}, None
    with open(path, encoding="utf-8") as file:
        for line in file.read().splitlines():
            if line == "## end":
                command = None
            elif line.startswith("## make "):
                command = line[3:]
                entries[command] = [None, []]
            elif line.startswith("## exit: "):
                entries[command][0] = int(line[len("## exit: "):])
            elif command is not None:
                entries[command][1].append(line)
            else:
                header.append(line)
    return header, {c: (e[0], e[1]) for c, e in entries.items()}


def run_make(argv: list, root: str = RIOTBASE) -> tuple:
    """(exit status, normalised output lines) of one Make run in the tree
    `root`. stdout and stderr are merged: the build command list ends with
    Make's error."""
    res = subprocess.run(argv, cwd=root, env=environment(), check=False,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return res.returncode, normalize(res.stdout, root).splitlines()
