# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G2B-1 (terminal without Make) and the golden files of GNU
Make.

The applications of the scope on nrf52840dk and, for each, the cases: every
terminal Make offers for the board (RIOT_TERMINAL), the port cases (the
programmer bmp, PORT from the command line and the environment,
MOST_RECENT_PORT=1 with and without a TTY found, macOS), `cleanterm`, and
the error cases. A golden file holds per case:

  ## <case>: make -n <goal> [...]     the commands of the target
  ## <case>: terminal call [...]      `make <goal>` with a recorder in place of
                                      the terminal program (in the tree for
                                      the scripts of dist/tools, on PATH for
                                      picocom, socat, Jelly, miniterm, the
                                      image for native): its arguments, the
                                      variables it gets (TERM_READS) and the
                                      calls of ttys.py

Stubs: `date` prints DATE (E8), `python3` answers for
dist/tools/usb-serial/ttys.py (TTY_ANSWER, or fails) and runs the real
Python otherwise; USER is fixed. Paths: @RIOTBASE@, @BINDIR@, @BINDIRBASE@,
@STUBS@, @HOME@, @TMP@. The file ends with `## end`.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import sys

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
APP_NAMES = {
    "examples/basic/hello-world": "hello-world",
    "examples/networking/gnrc/networking": "gnrc_networking",
    "examples/advanced/bindist": "bindist",
}
DATE = "2026-01-02_03.04.05"
USER = "riot"
TTY_ANSWER = "/dev/ttyACM7 000683654321"
# terminal programs found on PATH (stubs): the recorder
PATH_TERMINALS = ("picocom", "socat", "Jelly", "miniterm")
# terminal scripts of the tree: replaced by the recorder while the golden
# files are recorded (TERMPROG and DEBUGGER of the cases)
TREE_TERMINALS = ("dist/tools/pyterm/pyterm", "dist/tools/jlink/jlink.sh",
                  "dist/tools/openocd/openocd.sh", "dist/tools/bmp/bmp.py")

# The variables the terminal programs read from the environment: pyterm
# (HOME), dist/tools/jlink/jlink.sh (term-rtt, debug), dist/tools/openocd/
# openocd.sh (term-rtt, debug: the defaults at the top, test_config, do_term,
# do_debug, do_debugclient); picocom, socat, Jelly, miniterm and bmp.py read
# only their arguments.
TERM_READS = sorted({
    "HOME", "PYTERMFLAGS", "RIOTTOOLS", "BAUD",
    "FLASH_ADDR", "JLINK", "JLINK_DEVICE", "JLINK_IF", "JLINK_SERIAL", "JLINK_SERVER",
    "JLINK_SKIP_VERSION", "JLINK_SPEED", "JLINK_TERMFLAGS", "JLINK_TERMPROG",
    "DBG", "DBG_DEFAULT_FLAGS", "DBG_EXTRA_FLAGS", "DBG_FLAGS", "GDB", "GDB_PORT",
    "GDB_PORT_CORE_OFFSET", "TELNET_PORT", "TCL_PORT", "SETSID", "TUI",
    "OPENOCD", "OPENOCD_ADAPTER_INIT", "OPENOCD_CONFIG", "OPENOCD_CORE",
    "OPENOCD_DBG_EXTRA_CMD", "OPENOCD_DBG_START_CMD", "OPENOCD_EXTRA_INIT",
    "OPENOCD_SERVER_ADDRESS", "OPENOCD_TERMFLAGS", "OPENOCD_TERMPROG", "RAM_LEN",
    "RAM_START_ADDR", "RTT_PORT"})


def case(goal="term", variables=None, env=None, tty=None, path=PATH_TERMINALS, status=0,
         apps=tuple(APPS)):
    """A case: goal, command line variables, environment variables, the
    answer of ttys.py (None: not asked, "found", "none"), the PATH terminals
    present, the exit status of the recorder, the applications."""
    return {"goal": goal, "vars": dict(variables or {}), "env": dict(env or {}), "tty": tty,
            "path": tuple(path), "status": status, "apps": tuple(apps)}


HELLO = ("hello-world",)
CASES = {
    # E1: every terminal of nrf52840dk
    "pyterm": case(),
    "picocom": case(variables={"RIOT_TERMINAL": "picocom"}),
    "socat": case(variables={"RIOT_TERMINAL": "socat"}),
    "miniterm": case(variables={"RIOT_TERMINAL": "miniterm"}),
    "jelly": case(variables={"RIOT_TERMINAL": "jelly"}),
    "jlink": case(variables={"RIOT_TERMINAL": "jlink", "PROGRAMMER": "jlink"}),
    "openocd-rtt": case(variables={"RIOT_TERMINAL": "openocd-rtt"}),
    "semihosting": case(variables={"RIOT_TERMINAL": "semihosting"}),
    "semihosting-jlink": case(variables={"RIOT_TERMINAL": "semihosting", "PROGRAMMER": "jlink"}),
    "semihosting-bmp": case(variables={"RIOT_TERMINAL": "semihosting", "PROGRAMMER": "bmp"}),
    "native": case(variables={"RIOT_TERMINAL": "native"}),
    # E2: the port
    "bmp": case(variables={"PROGRAMMER": "bmp"}),
    "port": case(variables={"PORT": "/dev/ttyUSB3"}),
    "port-env": case(env={"PORT": "/dev/ttyUSB4"}),
    "terminal-env": case(env={"RIOT_TERMINAL": "picocom"}),
    "most-recent": case(variables={"MOST_RECENT_PORT": "1"}, tty="found"),
    "most-recent-jlink": case(variables={"MOST_RECENT_PORT": "1", "RIOT_TERMINAL": "jlink",
                                         "PROGRAMMER": "jlink"}, tty="found"),
    "most-recent-openocd-rtt": case(variables={"MOST_RECENT_PORT": "1",
                                               "RIOT_TERMINAL": "openocd-rtt"}, tty="found"),
    "most-recent-none": case(variables={"MOST_RECENT_PORT": "1"}, tty="none"),
    "darwin": case(variables={"OS": "Darwin"}, apps=HELLO),
    "darwin-bmp": case(variables={"OS": "Darwin", "PROGRAMMER": "bmp"}, apps=HELLO),
    "darwin-socat": case(variables={"OS": "Darwin", "RIOT_TERMINAL": "socat"}, apps=HELLO),
    "termlog": case(variables={"TERMLOG": "@TMP@/term.log"}, apps=HELLO),
    "docker": case(variables={"BUILD_IN_DOCKER": "1"}, apps=HELLO),
    # E5: cleanterm
    "cleanterm": case(goal="cleanterm"),
    "cleanterm-flags": case(goal="cleanterm", variables={"PYTERMFLAGS": "-x"}, apps=HELLO),
    "cleanterm-env-flags": case(goal="cleanterm", env={"PYTERMFLAGS": "-y"}, apps=HELLO),
    "cleanterm-jlink": case(goal="cleanterm", variables={"RIOT_TERMINAL": "jlink",
                                                         "PROGRAMMER": "jlink"}, apps=HELLO),
    # E6: errors
    "miniterm-missing": case(variables={"RIOT_TERMINAL": "miniterm"}, path=(), apps=HELLO),
    "picocom-missing": case(variables={"RIOT_TERMINAL": "picocom"}, path=(), apps=HELLO),
    "terminal-fails": case(variables={"RIOT_TERMINAL": "picocom"}, status=1, apps=HELLO),
}


def cases(app: str) -> dict:
    return {name: c for name, c in CASES.items() if app in c["apps"]}


def golden_path(app: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{BOARD}.txt")


def resolve(value: str, tmp: str) -> str:
    return value.replace("@TMP@", tmp)


def make_argv(app_dir: str, c: dict, bindirbase: str, tmp: str, extra: list) -> list:
    return (["make", "--no-print-directory", "-C", app_dir, f"BOARD={BOARD}",
             f"BINDIRBASE={bindirbase}"]
            + [f"{k}={resolve(v, tmp)}" for k, v in c["vars"].items()] + extra)


def title(name: str, app_dir: str, c: dict, what: str) -> str:
    shown = " ".join(shlex.quote(f"{k}={v}") for k, v in c["vars"].items())
    env = " ".join(shlex.quote(f"env:{k}={v}") for k, v in c["env"].items())
    words = " ".join(w for w in (app_dir, shown, env) if w)
    return f"## {name}: {what} [{words}]"


# --- stubs ------------------------------------------------------------------------
RECORDER = """#!/bin/sh
# recorder in place of a terminal program (step G2B-1 tests)
{{
  printf 'terminal %s' "$0"
  for a in "$@"; do printf ' [%s]' "$a"; done
  printf '\\n'
  for n in {names}; do
    eval "set=\\${{$n+x}}"
    if [ -n "$set" ]; then eval "printf '%s=[%s]\\n' $n \\"\\$$n\\""; else printf '%s unset\\n' $n; fi
  done
}} >> "$G2B_TERM_LOG"
if [ -n "$G2B_TERM_STDIN" ]; then cat > "$G2B_TERM_STDIN"; fi
exit "${{G2B_TERM_STATUS:-0}}"
"""

DATE_STUB = "#!/bin/sh\n# stub of date (step G2B-1 tests, E8)\necho {date}\n"

PYTHON_STUB = """#!/bin/sh
# stub of python3 (step G2B-1 tests): answers for usb-serial/ttys.py, runs
# the real Python for everything else
case "$1" in
  */usb-serial/ttys.py)
    {{ printf 'ttys.py'; shift; for a in "$@"; do printf ' [%s]' "$a"; done; printf '\\n'; }} \\
        >> "${{G2B_TTY_LOG:-/dev/null}}"
    [ "$G2B_TTY" = found ] && {{ echo '{answer}'; exit 0; }}
    exit 1 ;;
esac
exec {python} "$@"
"""


def write_executable(path: str, text: str):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def recorder() -> str:
    return RECORDER.format(names=" ".join(TERM_READS))


def real_python() -> str:
    return shutil.which("python3") or sys.executable


def make_stubs(root: str, path_terminals) -> dict:
    """`probe` (date, python3) and `term` (the PATH terminals of the case)."""
    dirs = {"probe": os.path.join(root, "probe"), "term": os.path.join(root, "term")}
    for directory in dirs.values():
        os.makedirs(directory, exist_ok=True)
    write_executable(os.path.join(dirs["probe"], "date"), DATE_STUB.format(date=DATE))
    write_executable(os.path.join(dirs["probe"], "python3"),
                     PYTHON_STUB.format(answer=TTY_ANSWER, python=real_python()))
    for name in path_terminals:
        write_executable(os.path.join(dirs["term"], name), recorder())
    return dirs


def stub_path(dirs: dict) -> str:
    return os.pathsep.join([dirs["probe"], dirs["term"], "/usr/local/bin", "/usr/bin", "/bin"])


def environment(path: str, home: str, c: dict, tmp: str, **extra) -> dict:
    env = {"PATH": path, "HOME": home, "LC_ALL": "C", "USER": USER, "TMPDIR": tmp}
    env.update({k: resolve(v, tmp) for k, v in c["env"].items()})
    if c["tty"]:
        env["G2B_TTY"] = c["tty"]
    if c["status"]:
        env["G2B_TERM_STATUS"] = str(c["status"])
    env.update(extra)
    return env


def fake_image(bindir: str, app_dir: str) -> str:
    """The image of the application: the recorder (RIOT_TERMINAL=native runs
    it; the others only name it)."""
    os.makedirs(bindir, exist_ok=True)
    elf = os.path.join(bindir, APP_NAMES[app_dir] + ".elf")
    write_executable(elf, recorder())
    return elf


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


def status_and_lines(body: list) -> tuple:
    status = int(body[0].split(":", 1)[1]) if body and body[0].startswith("## exit:") else None
    return status, [line for line in body[1:] if line]
