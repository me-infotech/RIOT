# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G2B-2 (debugger without Make), the stub tools and the
run protocol shared by the golden recorder and the tests.

The applications of the scope on nrf52840dk (term's sample) and, for each,
the three programmers (openocd, jlink, bmp) with the three targets (debug,
debug-server, debug-client); for hello-world also the default programmer,
the environment, MOST_RECENT_PORT=1, gdb-multiarch, the macOS setsid and the
error cases. A golden file holds per case:

  ## <case>: make -n <goal> [...]   the commands of the target
  ## <case>: run [...]              `make <goal>` with the real scripts of
                                    dist/tools and stub tools on PATH: the
                                    output, the call of each stub (arguments
                                    and the variables of DEBUG_READS) and the
                                    servers left running after the call

Stub tools (STUBS): openocd and JLinkGDBServer (servers: log, write their
pid, run until killed or told to stop), arm-none-eabi-gdb and gdb-multiarch
(log, survive SIGINT, read stdin until `quit` or EOF), JLinkExe (prints
`DLL version V7.94`), pipx (bmp.py's interpreter, log only), setsid (log,
then the real setsid); date and python3 for ttys.py come from term's
sample. Nothing reaches a probe or the network. Paths: @RIOTBASE@,
@BINDIR@, @BINDIRBASE@, @STUBS@, @HOME@, @TMP@. The file ends with `## end`.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.append(os.path.join(os.path.dirname(TOOL), "term", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(TOOL), "term"))
sys.path.insert(0, TOOL)

# pylint: disable=wrong-import-position
import sample as TS  # noqa: E402  (term's sample: stubs, golden format)

RIOTBASE = TS.RIOTBASE
GOLDEN = os.path.join(HERE, "golden")
BOARD = TS.BOARD
APPS = TS.APPS
APP_NAMES = TS.APP_NAMES
CLI = os.path.join(TOOL, "debug.py")
PROGRAMMERS = ("openocd", "jlink", "bmp")
GOALS = ("debug", "debug-server", "debug-client")
# the variables the debugger scripts and their tools read (term's list, the
# adapter serial and the bmp options)
DEBUG_READS = sorted(set(TS.TERM_READS) | {"DEBUG_ADAPTER_ID", "BMP_OPTIONS", "ELFFILE",
                                           "PROGRAMMER"})
STUB_ORDER = ("setsid", "JLinkExe", "openocd", "JLinkGDBServer", "arm-none-eabi-gdb",
              "gdb-multiarch", "pipx")
ALL_TOOLS = ("setsid", "JLinkExe", "openocd", "JLinkGDBServer", "arm-none-eabi-gdb", "pipx")
SERVERS = ("openocd", "JLinkGDBServer")
# the name mktemp gives the pid file of openocd.sh
MKTEMP_RE = re.compile(r"(openocd_pid)\.[A-Za-z0-9]{10}")


def case(goal="debug", variables=None, env=None, tools=ALL_TOOLS, tty=None, apps=tuple(APPS),
         server=None, elf=True, nosetsid=False, outside=False, server_status=0, record=True,
         board=BOARD, error=None):
    """A case: goal, command line and environment variables, the stub tools
    on PATH, the answer of ttys.py, the applications, the server stub that
    must have started before stdin is closed (None: none), whether the
    image exists, PATH without any setsid, `outside` (debug.py exits 3;
    only `make -n` is recorded), the exit status of the server stubs,
    `record` (False: Make is not run for it, e.g. PyCortexMDebug, whose
    checkout Make would fetch), `error` (Make's `$(error)` text; exit 2, only
    `make -n` is recorded)."""
    return {"goal": goal, "vars": dict(variables or {}), "env": dict(env or {}),
            "tools": tuple(tools), "tty": tty, "apps": tuple(apps), "server": server,
            "elf": elf, "nosetsid": nosetsid, "outside": outside,
            "server_status": server_status, "record": record, "board": board,
            "error": error}


def _matrix() -> dict:
    out = {}
    server = {"openocd": "openocd", "jlink": "JLinkGDBServer", "bmp": None}
    for programmer in PROGRAMMERS:
        for goal in GOALS:
            started = server[programmer] if goal in ("debug", "debug-server") else None
            out[f"{programmer}-{goal}"] = case(goal, {"PROGRAMMER": programmer},
                                               server=started)
    return out


HELLO = ("hello-world",)
NO_JLINK = tuple(t for t in ALL_TOOLS if t != "JLinkExe")
CASES = dict(_matrix())
CASES.update({
    # D2: the default programmer (jlink when JLinkExe is found, else openocd)
    "default-openocd": case(tools=NO_JLINK, server="openocd", apps=HELLO),
    "default-jlink": case(server="JLinkGDBServer", apps=HELLO),
    # environment variables as Make takes them
    "programmer-env": case(env={"PROGRAMMER": "jlink"}, server="JLinkGDBServer", apps=HELLO),
    "extra-cmd": case(variables={"PROGRAMMER": "openocd",
                                 "OPENOCD_DBG_EXTRA_CMD": "-c 'echo x'"},
                      server="openocd", apps=HELLO),
    # D9: MOST_RECENT_PORT=1 (the adapter serial from ttys.py)
    "most-recent-openocd": case(variables={"PROGRAMMER": "openocd", "MOST_RECENT_PORT": "1"},
                                tty="found", server="openocd", apps=HELLO),
    "most-recent-jlink": case(variables={"PROGRAMMER": "jlink", "MOST_RECENT_PORT": "1"},
                              tty="found", server="JLinkGDBServer", apps=HELLO),
    # GDB: gdb-multiarch when $(PREFIX)gdb is not found
    "gdb-multiarch": case(variables={"PROGRAMMER": "openocd"}, server="openocd",
                          tools=NO_JLINK[:-2] + ("gdb-multiarch", "pipx"), apps=HELLO),
    # D4: macOS: setsid found (no DEBUGDEPS), debug-server without the rule
    "darwin-setsid": case(variables={"PROGRAMMER": "openocd", "OS": "Darwin"},
                          server="openocd", apps=HELLO),
    "darwin-server-nosetsid": case("debug-server", {"PROGRAMMER": "jlink", "OS": "Darwin"},
                                   tools=("JLinkExe", "JLinkGDBServer"), nosetsid=True,
                                   server="JLinkGDBServer", apps=HELLO),
    # errors: exit 2 as Make
    "elf-missing": case(variables={"PROGRAMMER": "openocd"}, elf=False, apps=HELLO),
    "server-fails": case("debug-server", {"PROGRAMMER": "jlink"}, server_status=1,
                         apps=HELLO),
    "debugger-missing": case(variables={"PROGRAMMER": "openocd",
                                        "DEBUGGER": "no-such-debugger"}, apps=HELLO),
    "unknown-programmer": case(variables={"PROGRAMMER": "nosuch"}, apps=HELLO,
                               error="FLASHFILE is not defined for this board: nrf52840dk"),
    "pipx-missing": case(variables={"PROGRAMMER": "bmp"},
                         tools=("setsid", "JLinkExe", "arm-none-eabi-gdb"), apps=HELLO),
    # outside the data: exit 3 (D2, D3, board without data)
    "pyocd": case(variables={"PROGRAMMER": "pyocd"}, outside=True, apps=HELLO),
    "pycortexmdebug": case(variables={"PROGRAMMER": "openocd", "USE_PYCORTEXMDEBUG": "1"},
                           outside=True, record=False, apps=HELLO),
    "emulate": case(variables={"EMULATE": "1"}, outside=True, apps=HELLO),
    "darwin-nosetsid": case(variables={"PROGRAMMER": "openocd", "OS": "Darwin"},
                            tools=(), nosetsid=True, outside=True, apps=HELLO),
    "native64": case(outside=True, apps=HELLO, board="native64"),
})


def term_test_module(name: str):
    """A test module of term (its helpers), loaded under another name."""
    import importlib.util   # pylint: disable=import-outside-toplevel
    path = os.path.join(os.path.dirname(TOOL), "term", "tests", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"term_tests_{name}", path)
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved          # its own directory stays behind this one
    return module


def cases(app: str) -> dict:
    return {name: c for name, c in CASES.items() if app in c["apps"]}


def golden_path(app: str) -> str:
    return os.path.join(GOLDEN, f"{app}__{BOARD}.txt")


def title(name: str, app_dir: str, c: dict, what: str) -> str:
    return TS.title(name, app_dir, c, what)


# --- stubs ------------------------------------------------------------------------
LOG = """{{
  printf '%s' "$(basename "$0")"
  for a in "$@"; do printf ' [%s]' "$a"; done
  printf '\\n'
  for n in {names}; do
    eval "set=\\${{$n+x}}"
    if [ -n "$set" ]; then eval "printf '  %s=[%s]\\n' $n \\"\\$$n\\""; fi
  done
}} >> "$G2B_DBG_DIR/$(basename "$0").log"
"""
SERVER = """#!/bin/sh
# stub of a GDB server (step G2B-2 tests)
{log}echo "$(basename "$0") $$" >> "$G2B_DBG_DIR/servers.pid"
[ -n "$G2B_SERVER_STATUS" ] && exit "$G2B_SERVER_STATUS"
i=0
while [ $i -lt 600 ] && [ ! -e "$G2B_DBG_DIR/stop" ]; do sleep 0.1; i=$((i+1)); done
exit 0
"""
GDB = """#!/bin/sh
# stub of GDB (step G2B-2 tests): Ctrl+C does not end it (GDB stops the
# target instead), reads commands until quit or EOF
case "$1" in -v|--version) echo "GNU gdb (stub) 99"; exit 0 ;; esac
{log}echo "$(basename "$0") $$" >> "$G2B_DBG_DIR/gdb.pid"
trap '' INT
while IFS= read -r line; do
  echo "gdb: $line" >> "$G2B_DBG_DIR/$(basename "$0").log"
  [ "$line" = quit ] && break
done
exit 0
"""
JLINK = """#!/bin/sh
# stub of J-Link Commander (step G2B-2 tests)
{log}echo "SEGGER J-Link Commander V7.94 (stub)"
echo "DLL version V7.94, compiled Jan  1 2026 00:00:00"
exit 0
"""
PIPX = """#!/bin/sh
# stub of pipx (step G2B-2 tests): records the call of bmp.py, runs nothing
{log}exit 0
"""
SETSID = """#!/bin/sh
# stub of setsid (step G2B-2 tests): records, then the real setsid
{log}exec {real} "$@"
"""


def real_setsid() -> str:
    for directory in ("/usr/bin", "/bin"):
        path = os.path.join(directory, "setsid")
        if os.access(path, os.X_OK):
            return path
    raise RuntimeError("setsid (util-linux) is needed by the tests")


def make_stubs(root: str, tools) -> dict:
    """`probe` (date, python3 of term's sample) and `tools` (the stubs of the case)."""
    dirs = TS.make_stubs(root, ())
    dirs["tools"] = os.path.join(root, "tools")
    os.makedirs(dirs["tools"], exist_ok=True)
    log = LOG.format(names=" ".join(DEBUG_READS))
    texts = {"openocd": SERVER, "JLinkGDBServer": SERVER, "arm-none-eabi-gdb": GDB,
             "gdb-multiarch": GDB, "JLinkExe": JLINK, "pipx": PIPX, "setsid": SETSID}
    for name in tools:
        TS.write_executable(os.path.join(dirs["tools"], name),
                            texts[name].replace("{log}", log).replace("{real}", real_setsid()))
    return dirs


def system_without_setsid(root: str) -> str:
    """A directory with the programs of /usr/bin and /bin except setsid (the
    PATH of the macOS cases without setsid)."""
    target = os.path.join(root, "nosetsid")
    os.makedirs(target, exist_ok=True)
    for directory in ("/usr/bin", "/bin"):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            link = os.path.join(target, name)
            if name != "setsid" and not os.path.lexists(link):
                os.symlink(os.path.join(directory, name), link)
    return target


def stub_path(dirs: dict, nosetsid_dir=None) -> str:
    system = [nosetsid_dir] if nosetsid_dir else ["/usr/local/bin", "/usr/bin", "/bin"]
    if nosetsid_dir and os.path.isdir("/usr/local/bin") and \
            not os.path.exists("/usr/local/bin/setsid"):
        system.insert(0, "/usr/local/bin")
    return os.pathsep.join([dirs["probe"], dirs["tools"]] + system)


def make_argv(app_dir: str, c: dict, board: str, bindirbase: str, extra: list) -> list:
    return (["make", "--no-print-directory", "-C", app_dir, f"BOARD={board}",
             f"BINDIRBASE={bindirbase}"] + [f"{k}={v}" for k, v in c["vars"].items()] + extra)


def tool_argv(app_dir: str, c: dict, board: str, bindirbase: str, options=()) -> list:
    return ([sys.executable, CLI, c["goal"], *options, "-C", app_dir, f"BOARD={board}",
             f"BINDIRBASE={bindirbase}"] + [f"{k}={v}" for k, v in c["vars"].items()])


class Run:
    """The temporary directory of one case: HOME, the image, the stubs."""

    def __init__(self, root: str, app_dir: str, c: dict, tmp: str):
        self.root, self.app_dir, self.c, self.tmp = root, app_dir, c, tmp
        self.board = board = c["board"]
        self.home = os.path.join(tmp, "home")
        os.makedirs(self.home, exist_ok=True)
        self.bindirbase = os.path.join(tmp, "bin")
        self.bindir = os.path.join(self.bindirbase, board)
        self.stubs = os.path.join(tmp, "stubs")
        self.dbg = os.path.join(tmp, "dbg")
        os.makedirs(self.dbg, exist_ok=True)
        dirs = make_stubs(self.stubs, c["tools"])
        self.path = stub_path(dirs, system_without_setsid(self.stubs) if c["nosetsid"]
                              else None)
        self.tty_log = os.path.join(tmp, "tty.log")
        self.pairs = [(root, "@RIOTBASE@"), (self.bindir, "@BINDIR@"),
                      (self.bindirbase, "@BINDIRBASE@"), (self.stubs, "@STUBS@"),
                      (self.home, "@HOME@"), (tmp, "@TMP@")]
        if c["elf"]:
            os.makedirs(self.bindir, exist_ok=True)
            with open(os.path.join(self.bindir, APP_NAMES[app_dir] + ".elf"), "w",
                      encoding="utf-8") as file:
                file.write("not an ELF file (step G2B-2 tests)\n")

    def norm(self, text: str) -> str:
        return MKTEMP_RE.sub(r"\1.@XXXXXXXXXX@", TS.normalise(text, self.pairs))

    def env(self, **extra) -> dict:
        env = TS.environment(self.path, self.home, {"env": self.c["env"], "tty": self.c["tty"],
                                                    "status": 0}, self.tmp,
                             G2B_DBG_DIR=self.dbg, G2B_TTY_LOG=self.tty_log, **extra)
        if self.c["server_status"]:
            env["G2B_SERVER_STATUS"] = str(self.c["server_status"])
        return env

    def make_argv(self, extra: list) -> list:
        return make_argv(self.app_dir, self.c, self.board, self.bindirbase, extra)

    def tool_argv(self, options=()) -> list:
        return tool_argv(self.app_dir, self.c, self.board, self.bindirbase, options)

    def capture(self, argv: list) -> tuple:
        res = subprocess.run(argv, cwd=self.root, env=self.env(), capture_output=True,
                             text=True, stdin=subprocess.DEVNULL, check=False)
        return res.returncode, res.stdout, res.stderr

    # -- the run protocol: stdin is a pipe, closed once the server started
    def servers(self) -> list:
        path = os.path.join(self.dbg, "servers.pid")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as file:
            return [(line.split()[0], int(line.split()[1])) for line in file if line.strip()]

    def wait_server(self, timeout=20.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.servers():
                time.sleep(0.4)          # the script writes its pid file next
                return True
            time.sleep(0.05)
        return False

    def run(self, argv: list, timeout=60.0) -> tuple:
        """(exit status, output lines, stub lines): the protocol of the golden
        `run` section."""
        out_path = os.path.join(self.tmp, "out.txt")
        with open(out_path, "w", encoding="utf-8") as out:
            proc = subprocess.Popen(argv, cwd=self.root, env=self.env(),  # pylint: disable=consider-using-with
                                    stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT)
            if self.c["server"] and not self.c["server_status"]:
                self.wait_server()
            proc.stdin.close()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                open(os.path.join(self.dbg, "stop"), "w", encoding="utf-8").close()
                proc.wait(timeout=timeout)
        time.sleep(0.3)
        left = [name for name, pid in self.servers() if alive(pid)]
        self.stop_servers()
        with open(out_path, encoding="utf-8") as file:
            out = [f"out: {line}" for line in self.norm(file.read()).split("\n")
                   if line and not line.startswith("make: ***")]
        return proc.returncode, out, self.stub_lines() + [f"left running: {' '.join(left)}"]

    def stub_lines(self) -> list:
        lines = []
        for name in STUB_ORDER:
            path = os.path.join(self.dbg, f"{name}.log")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as file:
                    lines += [self.norm(line) for line in file.read().split("\n") if line]
        if os.path.exists(self.tty_log):
            with open(self.tty_log, encoding="utf-8") as file:
                lines += [self.norm(line) for line in file.read().split("\n") if line]
        return lines

    def stop_servers(self):
        """The servers of the case end (orphans included): the stop file,
        then SIGKILL for any left."""
        open(os.path.join(self.dbg, "stop"), "w", encoding="utf-8").close()
        end = time.monotonic() + 3.0
        while time.monotonic() < end and any(alive(p) for _, p in self.servers()):
            time.sleep(0.05)
        for _, pid in self.servers():
            if alive(pid):
                os.kill(pid, signal.SIGKILL)


def alive(pid: int) -> bool:
    """The process exists and is no zombie."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as file:
            return file.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return False


