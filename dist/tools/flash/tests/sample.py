# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G3-2 (flash without Make) and the golden files of GNU Make.

The applications of the scope on nrf52840dk (decision D22) and, for each,
the cases: every programmer the board supports (jlink, openocd, bmp), the
board's default with and without J-Link Commander on PATH, and (hello-world)
variants with command line variables. A golden file holds per case:

  ## <case>: make … -n -o all flash          the commands of `flash` after `all`
                                             (`-o all`: the build itself is the
                                             parity of step G3-1)
  ## <case>: flasher environment             what the flasher script gets (a
                                             recorder in place of the script)
  ## <case>: stub calls                      the real flasher script run with
                                             stub tools on PATH (JLinkExe,
                                             openocd, pipx): their arguments and
                                             the J-Link command file

Paths: @RIOTBASE@, @BINDIR@ (the directory of the image), @STUBS@. The file
ends with `## end`.
"""

from __future__ import annotations

import os
import shlex
import stat

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLDEN = os.path.join(HERE, "golden")
BOARD = "nrf52840dk"
APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
# name -> (command line variables, J-Link Commander on PATH)
CASES = {
    "default": ({}, False),
    "default-jlink-found": ({}, True),
    "jlink": ({"PROGRAMMER": "jlink"}, True),
    "openocd": ({"PROGRAMMER": "openocd"}, False),
    "bmp": ({"PROGRAMMER": "bmp"}, False),
}
EXTRA_CASES = {   # hello-world only
    "jlink-serial": ({"PROGRAMMER": "jlink", "DEBUG_ADAPTER_ID": "000683123456"}, True),
    "jlink-wrapper": ({"PROGRAMMER": "jlink", "USE_PROGRAMMER_WRAPPER_SCRIPT": "1"}, True),
    "openocd-serial": ({"PROGRAMMER": "openocd", "DEBUG_ADAPTER_ID": "000683123456"}, False),
    "openocd-offset": ({"PROGRAMMER": "openocd", "OPENOCD_SKIP_VERIFY": "1",
                        "IMAGE_OFFSET": "0x1000"}, False),
    "bmp-options": ({"PROGRAMMER": "bmp", "BMP_OPTIONS": "--port /dev/ttyACM0"}, False),
}
SUPPORTED = ["jlink", "openocd", "bmp"]

# The variables the flash action of each flasher script reads (the rest of
# the scripts is debug, reset, terminal): dist/tools/jlink/jlink.sh
# test_config/test_serial/test_version/flash_common/do_flash_*, and
# dist/tools/openocd/openocd.sh the defaults at the top, test_config,
# _flash_address and do_flash. bmp.py and programmer.py read none (only
# their arguments).
FLASHER_READS = {
    "dist/tools/jlink/jlink.sh": [
        "BINDIR", "FLASH_ADDR", "IMAGE_OFFSET", "JLINK", "JLINK_DEVICE", "JLINK_IF",
        "JLINK_POST_FLASH", "JLINK_PRE_FLASH", "JLINK_RESET_FILE", "JLINK_SERIAL",
        "JLINK_SKIP_VERSION", "JLINK_SPEED", "RIOTTOOLS"],
    "dist/tools/openocd/openocd.sh": [
        "IMAGE_OFFSET", "IMAGE_TYPE", "OPENOCD", "OPENOCD_ADAPTER_INIT", "OPENOCD_CMD_RESET_HALT",
        "OPENOCD_CONFIG", "OPENOCD_EXTRA_INIT", "OPENOCD_EXTRA_RESET_INIT",
        "OPENOCD_POST_INIT_CMDS", "OPENOCD_PRE_FLASH_CHECK_SCRIPT", "OPENOCD_PRE_FLASH_CMDS",
        "OPENOCD_PRE_VERIFY_CMDS", "OPENOCD_RESET_USE_CONNECT_ASSERT_SRST",
        "OPENOCD_SKIP_VERIFY", "RIOTTOOLS"],
    "dist/tools/bmp/bmp.py": [],
    "dist/tools/programmer/programmer.py": [],
}
ENV_NAMES = sorted(set(n for names in FLASHER_READS.values() for n in names))
STUB_TOOLS = ("JLinkExe", "openocd", "pipx")


def cases(app: str) -> dict:
    return dict(CASES, **EXTRA_CASES) if app == "hello-world" else dict(CASES)


def golden_path(app: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{BOARD}.txt")


def make_argv(app_dir: str, variables: dict, bindirbase: str, extra: list) -> list:
    return (["make", "--no-print-directory", "-C", app_dir, f"BOARD={BOARD}",
             f"BINDIRBASE={bindirbase}"] + [f"{k}={v}" for k, v in variables.items()] + extra)


def title(case: str, app_dir: str, variables: dict, what: str) -> str:
    shown = " ".join(shlex.quote(f"{k}={v}") for k, v in variables.items())
    return f"## {case}: {what} [{app_dir}{' ' + shown if shown else ''}]"


# --- stub tools ------------------------------------------------------------------
STUB = """#!/bin/sh
# stub of {tool} (step G3-2 tests): records its arguments
{{
  printf '%s' '{tool}'
  for a in "$@"; do printf ' [%s]' "$a"; done
  printf '\\n'
}} >> "$G3_STUB_LOG"
prev=
for a in "$@"; do
  if [ "$prev" = "-commandfile" ] && [ -f "$a" ]; then
    sed 's/^/  commandfile: /' "$a" >> "$G3_STUB_LOG"
  fi
  prev="$a"
done
case " $* " in
  *" -nogui 1"*) [ "{tool}" = JLinkExe ] && ! printf '%s' "$*" | grep -q commandfile \\
      && echo "DLL version V7.94e, compiled Jan 1 2026" ;;
esac
exit 0
"""

RECORDER = """#!/usr/bin/env python3
# recorder in place of a flasher script (golden files of step G3-2)
import os
import sys
NAMES = {names!r}
with open(os.environ["G3_ENV_LOG"], "a", encoding="utf-8") as log:
    log.write("flasher {name}" + "".join(f" [{{a}}]" for a in sys.argv[1:]) + "\\n")
    for n in NAMES:
        log.write(f"{{n}}=[{{os.environ[n]}}]\\n" if n in os.environ else f"{{n}} unset\\n")
"""


def write_executable(path: str, text: str):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_stubs(root: str) -> dict:
    """Two directories of stub tools: `jlink` holds JLinkExe (on PATH only
    when the case says so), `tools` the others."""
    dirs = {"jlink": os.path.join(root, "stub-jlink"), "tools": os.path.join(root, "stub-tools")}
    for directory in dirs.values():
        os.makedirs(directory, exist_ok=True)
    write_executable(os.path.join(dirs["jlink"], "JLinkExe"), STUB.format(tool="JLinkExe"))
    for tool in ("openocd", "pipx"):
        write_executable(os.path.join(dirs["tools"], tool), STUB.format(tool=tool))
    return dirs


def stub_path(dirs: dict, jlink_found: bool) -> str:
    parts = [dirs["tools"]] + ([dirs["jlink"]] if jlink_found else [])
    return os.pathsep.join(parts + [os.environ.get("PATH", "/usr/bin:/bin")])


def environment(path: str, **extra) -> dict:
    env = {"PATH": path, "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}
    env.update(extra)
    return env


def fake_image(bindir: str, app_dir: str) -> str:
    """The image the flasher is given (no toolchain here): a file with the
    ELF magic number."""
    os.makedirs(bindir, exist_ok=True)
    elf = os.path.join(bindir, APP_NAMES[app_dir] + ".elf")
    with open(elf, "wb") as file:
        file.write(b"\x7fELF")
    return elf


# APPLICATION of each sample application (the name of its image)
APP_NAMES = {
    "examples/basic/hello-world": "hello-world",
    "examples/networking/gnrc/networking": "gnrc_networking",
    "examples/advanced/bindist": "bindist",
}


def normalise(text: str, pairs: list) -> str:
    for path, name in sorted(pairs, key=lambda p: -len(p[0])):
        text = text.replace(path, name)
    return text


# --- golden files ------------------------------------------------------------------
def read_golden(path: str) -> tuple:
    """(header lines, {section title: [lines]})."""
    with open(path, encoding="utf-8") as file:
        lines = file.read().split("\n")
    if "## end" not in lines:
        raise ValueError(f"{path}: no `## end` line")
    lines = lines[:lines.index("## end")]
    first = next(i for i, line in enumerate(lines) if line.startswith("## "))
    head, sections, title_, body = lines[:first], {}, None, []
    for line in lines[first:]:
        if line.startswith("## ") and not line.startswith("## exit:"):
            if title_:
                sections[title_] = body
            title_, body = line, []
        else:
            body.append(line)
    if title_:
        sections[title_] = body
    return head, sections


def recipe_lines(body: list) -> tuple:
    """(exit status, command lines) of a `make -n` section."""
    status = int(body[0].split(":", 1)[1]) if body and body[0].startswith("## exit:") else None
    return status, [line for line in body[1:] if line]
