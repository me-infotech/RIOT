# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G3-1 and the golden files of GNU Make.

The applications of the scope on the board nrf52840dk (decision D22). The
golden files hold, for each application, what GNU Make does for `all`:

  ## make … -n -k (packages missing)     the commands with an empty BUILD_DIR
                                         (the package clone commands)
  ## make … -n -k (packages prepared)    the commands with prepared packages
                                         and riotbuild.h (compile, link, …)
  ## file riotbuild/riotbuild.h          the header Make generates
  ## file preprocessor/preprocessor_successor.h   its SHA-256 and lines

Paths are written as @RIOTBASE@, @BUILD_DIR@, @BINDIR@ (BINDIRBASE/BOARD),
@BINDIRBASE@. The file ends with the line `## end`.
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLDEN = os.path.join(HERE, "golden")
BOARD = "nrf52840dk"
APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
CC = "arm-none-eabi-gcc"
FRESH = "(packages missing)"
PREPARED = "(packages prepared)"
RIOTBUILD_H = "## file riotbuild/riotbuild.h"
PP_H = "## file preprocessor/preprocessor_successor.h"


def golden_path(app: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{BOARD}.txt")


def make_argv(app_dir: str, extra: list = ()) -> list:
    return ["make", "--no-print-directory", "-C", app_dir, f"BOARD={BOARD}", *extra]


def environment() -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}


def read_golden(path: str) -> tuple:
    """(header lines, {section title: text})."""
    with open(path, encoding="utf-8") as file:
        lines = file.read().split("\n")
    if "## end" not in lines:
        raise ValueError(f"{path}: no `## end` line")
    lines = lines[:lines.index("## end")]
    first = next(i for i, line in enumerate(lines) if line.startswith("## "))
    head = lines[:first]
    sections, title, body = {}, None, []
    for line in lines[len(head):]:
        if line.startswith("## ") and not line.startswith("## exit:"):
            if title:
                sections[title] = "\n".join(body)
            title, body = line, []
        else:
            body.append(line)
    if title:
        sections[title] = "\n".join(body)
    return head, sections


def section(sections: dict, suffix: str) -> str:
    for title, text in sections.items():
        if title.endswith(suffix):
            return text
    raise KeyError(suffix)
