# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Shared parts of the tests of step G0-3 (the build data is the only source
of the build flags; Make reads adapters generated from it)."""

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
TOOLS = os.path.dirname(TOOL)
for _sub in (TOOL, os.path.join(TOOLS, "resolver")):
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import generate  # noqa: E402
import rules as R  # noqa: E402

RIOTBASE = R.RIOTBASE
GOLDEN = os.path.join(HERE, "golden")
MAKE = shutil.which("make")
SCOPE = config_data.load_scope()
BUILD = SCOPE["build"]
# The commit the Make files were split from (G3-1 on the fork's master): the
# build part of these Make files is unchanged there (scope.yaml build_base).
BASE = SCOPE["build_base"]

APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
BOARD = "nrf52840dk"
PLACEHOLDER = "@RIOTBASE@"
VERSION_RE = re.compile(r'-DRIOT_VERSION=\\"[^\\"]*\\"')
# names of the git description: they name the commit and branch of the
# checkout, not a result of the build configuration
VERSION_VARS = ("GIT_DESCRIBE", "GIT_BRANCH", "_GIT_VERSION", "GIT_VERSION",
                "RIOT_VERSION_GIT", "RIOT_VERSION", "BUILD_GIT_BRANCH_STEM",
                "BUILD_GIT_BRANCH_SUFFIX")


def path(rel: str) -> str:
    return os.path.join(RIOTBASE, rel)


def read(rel: str) -> str:
    with open(path(rel), encoding="utf-8") as file:
        return file.read()


def rules_of(data: str) -> list:
    return config_data.load_valid(path(data))


def generated(data: str):
    """The generated Make file of a data file (relative) or None."""
    return config_data.build_target(data, BUILD[data])


def git_show(rev: str, rel: str):
    """The file at a revision, or None if the revision is not available."""
    res = subprocess.run(["git", "-C", RIOTBASE, "show", f"{rev}:{rel}"],
                         capture_output=True, text=True, check=False)
    return res.stdout if res.returncode == 0 else None


def code_lines(text: str) -> list:
    """The lines of a Make file without comments and blank lines, blanks
    collapsed."""
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(" ".join(stripped.split()))
    return out


# helpers the data introduced for Make text it cannot write directly (a
# `$(wildcard …)` inside another function); they did not exist before
DATA_HELPERS = ("BUILD_APP_INCLUDE_DIR", "BUILD_BOARD_INCLUDE_DIR", "BUILD_DISTCHECK")


def written_variables(rules: list) -> set:
    """Every variable a rule list sets, adds to or exports in Make (rules
    with `stand_in` are not part of the generated Make)."""
    names = set()
    for rule in R.walk(generate.for_make(rules)):
        if "set" in rule:
            names.add(rule["set"]["var"])
        if "add" in rule:
            names.update(rule["add"])
        names.update(rule.get("export") or [])
    return names - set(DATA_HELPERS)


def exported_variables(rules: list) -> set:
    names = set()
    for rule in R.walk(rules):
        names.update(rule.get("export") or [])
        if "set" in rule and rule["set"].get("export"):
            names.add(rule["set"]["var"])
    return names


def all_rules() -> list:
    out = []
    for data in sorted(BUILD):
        out += rules_of(data)
    return out


def environment() -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}


DUMP_MK = os.path.join(HERE, "dump.mk")


def make_values(root: str, app_dir: str, names: list, exported: list) -> list:
    """Make's expanded value of each variable after all Make files are read,
    and the exported environment of a recipe, normalised (lines
    `[VAR] value` and `ENV NAME=value`, no trailing blanks)."""
    argv = ["make", "--no-print-directory", "-C", os.path.join(root, app_dir), f"BOARD={BOARD}",
            "-f", "Makefile", "-f", DUMP_MK, f"G003_NAMES={' '.join(names)}",
            "riot-g003-env"]
    res = subprocess.run(argv, cwd=root, env=environment(), capture_output=True, text=True,
                         check=False)
    lines = []
    for line in res.stdout.split("\n"):
        line = line.replace(root, PLACEHOLDER)
        line = VERSION_RE.sub('-DRIOT_VERSION=\\"@VERSION@\\"', line)
        if line.startswith("G003 "):
            name = line[5:].split(" ", 1)[0]
            if name not in VERSION_VARS:
                value = line[5:].split(" = ", 1)[1] if " = " in line else ""
                lines.append(f"[{name}] {value}".rstrip())
        elif line.startswith("ENV "):
            name = line[4:].split("=", 1)[0]
            if name in exported and name not in VERSION_VARS:
                lines.append(line.rstrip())
    return [f"#STATUS {res.returncode}"] + lines
