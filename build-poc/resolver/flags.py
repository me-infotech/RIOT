#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Evaluate RIOT's Makefile.include as data (translated rules, decision
D26) for one application and board, without running Make: dependency
resolution, CFLAGS, INCLUDES, LINKFLAGS and the other variables the build
needs.

$(shell …) calls go through SHELL_BLOCKS: each known command pattern is a
named Python block; an unknown command stops the run and is reported, so
that every shell call the build relies on is visible.

Usage: flags.py <riot root> <rules.json> <riot-app.yaml> <board>
               [VAR …]   (default: CFLAGS INCLUDES LINKFLAGS)
"""

import json
import os
import re
import shutil
import struct
import subprocess
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import makeexpr  # noqa: E402
from resolver import MakeError, Resolver  # noqa: E402

SHELL_LOG: list = []


def shell_block(cmd: str) -> str:
    """Named Python blocks for the $(shell …) calls of the build."""
    c = " ".join(cmd.split())
    SHELL_LOG.append(c)
    for name, pattern, fn in SHELL_BLOCKS:
        m = re.fullmatch(pattern, c)
        if m:
            BLOCK_USE[name] = BLOCK_USE.get(name, 0) + 1
            return fn(m)
    if os.environ.get("FLAGS_DISCOVER") == "1":
        # discovery mode: run the command to see which calls exist
        return _run(re.fullmatch(r".*", c, re.S))
    raise makeexpr.UnsupportedExpr(f"no Python block for $(shell {c[:120]})")


def _run(m) -> str:
    """Blocks that run a host program whose output is the value (tool
    versions, git): same command, run directly without Make."""
    out = subprocess.run(m.group(0), shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True,
                         cwd=makeexpr.CWD).stdout
    return " ".join(out.split())


def sh_arith(expr: str) -> int:
    """$((…)) like /bin/sh: integers (decimal, 0x hex, leading-zero
    octal), unary + - ~ !, * / % (C: division truncates toward zero,
    remainder takes the sign of the dividend), + -, << >>, & ^ |,
    parentheses. Anything else (variables, comparisons, assignments)
    raises UnsupportedExpr."""
    tokens = re.findall(r"\s*(0[xX][0-9a-fA-F]+|\d+|<<|>>|[-+*/%()~!&^|]|\S)", expr)
    if "".join(t.strip() for t in tokens) != "".join(expr.split()):
        raise makeexpr.UnsupportedExpr(f"arithmetic {expr}")
    tokens = [t.strip() for t in tokens]
    pos = 0

    def bad():
        raise makeexpr.UnsupportedExpr(f"arithmetic {expr}")

    def number(t):
        if re.fullmatch(r"0[xX][0-9a-fA-F]+", t):
            return int(t, 16)
        if re.fullmatch(r"0[0-7]*", t):
            return int(t, 8)
        if re.fullmatch(r"[1-9]\d*", t):
            return int(t)
        bad()                                   # e.g. 08: error in sh

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def unary():
        t = take() if peek() is not None else bad()
        if t == "(":
            v = binary(0)
            if take() != ")":
                bad()
            return v
        if t in ("-", "+", "~", "!"):
            v = unary()
            return {"-": -v, "+": v, "~": ~v, "!": int(not v)}[t]
        return number(t)

    levels = [("|",), ("^",), ("&",), ("<<", ">>"), ("+", "-"), ("*", "/", "%")]

    def binary(level):
        if level == len(levels):
            return unary()
        v = binary(level + 1)
        while peek() in levels[level]:
            op = take()
            w = binary(level + 1)
            if op in ("/", "%"):
                if w == 0:
                    bad()                       # division by zero: sh error
                q = abs(v) // abs(w) * (1 if (v < 0) == (w < 0) else -1)
                v = q if op == "/" else v - w * q
            else:
                v = {"|": v | w, "^": v ^ w, "&": v & w, "<<": v << w,
                     ">>": v >> w, "+": v + w, "-": v - w, "*": v * w}[op]
        return v

    val = binary(0)
    if pos != len(tokens):
        bad()
    return val


def _arith(m) -> str:
    """echo $((…)) / printf "0x%x" $((…)) (sizes and addresses)."""
    val = sh_arith(m.group("e"))
    return f"0x{val:x}" if m.group("fmt") else str(val)


def _which(m) -> str:
    """command -v a [|| command -v b …]: first program found on PATH."""
    for prog in re.findall(r"command -v (\S+)", m.group(0)):
        path = shutil.which(prog)
        if path:
            return path
    return ""


def _tool_version(m) -> str:
    """command -v CC > /dev/null && CC -dumpversion"""
    prog = m.group("p")
    if not shutil.which(prog):
        return ""
    return _out([prog, "-dumpversion"])


def _out(argv, **kw) -> str:
    res = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, cwd=makeexpr.CWD, **kw)
    return " ".join(res.stdout.split())


def _exit_code(argv, stdin_null=True) -> str:
    res = subprocess.run(argv, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL if stdin_null else None,
                         cwd=makeexpr.CWD)
    return str(res.returncode)


def _probe_preprocess(m) -> str:
    """CC <flag> -E - …; echo $?: does the compiler accept the flag?"""
    return _exit_code([m.group("cc")] + m.group("flags").split() + ["-E", "-"])


def _probe_link(m) -> str:
    """LC_ALL=C CC minimal_linkable.c -o /dev/null … : linker output (empty
    if the flags are accepted)."""
    argv = m.group("rest").split()
    res = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, cwd=makeexpr.CWD,
                         env=dict(os.environ, LC_ALL="C"))
    return " ".join(res.stdout.split())


def _system_includes(m) -> str:
    """CC -v -x c -E /dev/null | sed …: the compiler's include search list."""
    res = subprocess.run([m.group("cc"), "-v", "-x", "c", "-E", "/dev/null"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
    lines, on = [], False
    for line in res.stdout.splitlines():
        if line.startswith("#include <...> search starts here:"):
            on = True
            continue
        if line.startswith("End of search list."):
            break
        if on:
            lines.append(line.strip())
    return " ".join(lines)


def _git_toplevel(m) -> str:
    out = _out(["git", "rev-parse", "--show-toplevel"])
    return out or makeexpr.CWD


# program names and flag words in the patterns: no shell metacharacters
PROG = r"[\w.+/-]+"
FLAG = r"(?:-[\w=,.+/-]+|noexecstack)"

# (name, regular expression over the whole command, block); every $(shell)
# of the build for hello-world/nrf52840dk is listed here (test log)
SHELL_BLOCKS: list = [
    ("getconf-long-bit", r"getconf LONG_BIT",
     lambda m: str(struct.calcsize("P") * 8)),
    ("uname", r"uname -m -s",
     lambda m: f"{os.uname().sysname} {os.uname().machine}"),
    ("arithmetic", r"(?P<fmt>printf \"0x%x\" )?(?:echo )?\$\(\((?P<e>[0-9a-fA-FxX+\-*/%()~!&^|<> ]*)\)\)",
     _arith),
    ("which", rf"command -v {PROG}( 2>/dev/null)?( \|\| command -v {PROG})*",
     _which),
    # the blocks below run the matched command on the host (tool versions,
    # toolchain probes); their patterns admit only the command shapes of
    # RIOT's make files with program names and flag words, no other shell
    ("tool-version", rf"command -v (?P<p>{PROG}) > /dev/null && (?P=p) -dumpversion",
     _run),
    ("git-toplevel", r"git rev-parse --show-toplevel 2>/dev/null \|\| pwd",
     _git_toplevel),
    # time stamp (pyterm log name in TERMFLAGS)
    ("date", r"date \+(?P<f>[%\w.:-]+)",
     lambda m: __import__("time").strftime(m.group("f"))),
    # version string (RIOT_VERSION): git describe / branch name
    ("git-describe", r'git --git-dir="(?P<d>[^"]+)" describe --always --abbrev=4 2> /dev/null',
     lambda m: _out(["git", f"--git-dir={m.group('d')}", "describe", "--always", "--abbrev=4"])),
    ("git-branch", r'git --git-dir="(?P<d>[^"]+)" rev-parse --abbrev-ref HEAD',
     lambda m: _out(["git", f"--git-dir={m.group('d')}", "rev-parse", "--abbrev-ref", "HEAD"])),
    # toolchain probes: the toolchain make files ask the compiler, linker
    # or debugger whether a flag works; the block runs the same probe
    # command of the host tool (stdout only, like $(shell))
    ("compiler-flag-probe",
     rf"{PROG}(?: {FLAG})+ -E - 2>/dev/null >/dev/null </dev/null ; echo \$\?", _run),
    ("gdb-probe", rf"{PROG}gdb -v > /dev/null 2>&1; echo \$\?", _run),
    ("linker-flag-probe",
     rf"LC_ALL=C {PROG} {PROG}/minimal_linkable\.c -o /dev/null(?: {FLAG})+"
     r"(?: 2> /dev/null && echo 1 \|\| echo 0"
     r'| 2>&1 \| grep -q "[\w\s.,-]+" ; echo \$\?)', _run),
    ("compiler-include-dirs",
     rf"{PROG} -v -x c -E /dev/null 2>&1 \| sed -e '1,/\\#include <\.\.\.> "
     r"search starts here:/d' -e '/End of search list\./,\$d' -e 's/\^ \*//'", _run),
]
BLOCK_USE: dict = {}


def evaluate(root: str, rules: dict, app_path: str, board: str) -> Resolver:
    """Evaluate Makefile.include for the application; raises on errors."""
    app = yaml.safe_load(open(app_path)) or {}
    appdir = os.path.dirname(os.path.abspath(app_path))
    r = Resolver(root, rules)
    makeexpr.CWD = appdir
    makeexpr.SHELL = shell_block
    s = r.s
    # variables Make defines itself (origin "default"/"file"), MAKELEVEL
    # from the environment (0 at the top level)
    for k, v in {"MAKE": "make", "MAKE_VERSION": "4.3",
                 "MAKECMDGOALS": ""}.items():
        s.set_simple(k, v, "default")
    for k, v in {"CURDIR": appdir, "SHELL": "/bin/sh",
                 "MAKEFILE_LIST": ""}.items():
        s.set_simple(k, v)
    s.set_env("MAKELEVEL", "0")
    for k, v in {"BOARD": board,
                 "APPLICATION": app.get("application", "")}.items():
        s.assign(k, ":=", v)
    keymap = {"usemodule": "USEMODULE", "usepkg": "USEPKG",
              "disable_module": "DISABLE_MODULE",
              "features_required": "FEATURES_REQUIRED",
              "features_required_any": "FEATURES_REQUIRED_ANY",
              "features_optional": "FEATURES_OPTIONAL",
              "features_blacklist": "FEATURES_BLACKLIST",
              "cflags": "CFLAGS"}
    for key, var in keymap.items():
        if app.get(key):
            s.assign(var, "+=", " ".join(app[key]))
    for key, var in {"develhelp": "DEVELHELP", "quiet": "QUIET",
                     "werror": "WERROR"}.items():
        if key in app:
            s.assign(var, "?=", str(app[key]))
    if "riotbase" in app:
        s.assign("RIOTBASE", "?=", os.path.normpath(os.path.join(appdir, str(app["riotbase"]))))
    for var, val in (app.get("app_defaults") or {}).items():
        s.assign(var, "?=", str(val))
    r.ENGINE = {}            # everything runs from data, incl. features_check
    r.include(f"{root}/Makefile.include", False, "flags")
    return r


def main() -> int:
    root, rules_path, app_path, board = sys.argv[1:5]
    wanted = sys.argv[5:] or ["CFLAGS", "INCLUDES", "LINKFLAGS"]
    rules = json.load(open(rules_path))
    try:
        r = evaluate(root, rules, app_path, board)
        s = r.s
    except (MakeError, makeexpr.UnsupportedExpr) as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"shell calls so far: {len(SHELL_LOG)}", file=sys.stderr)
        return 1
    out = {v: s.get(v) for v in wanted}
    out["_shell_calls"] = sorted(set(SHELL_LOG))
    out["_shell_blocks"] = BLOCK_USE
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
