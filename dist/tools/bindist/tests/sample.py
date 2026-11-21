# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G3-3 (bindist without Make) and the golden files of GNU Make.

The application examples/advanced/bindist (the one application of the scope
that names DIST_FILES and BIN_USEMODULE) on nrf52840dk (decision D22), in
cases with command line variables. The golden file holds per case:

  ## <case>: make -n -o all bindist          the commands of `bindist` after
                                             `all` (`-o all`: the build is the
                                             parity of step G3-1)
  ## <case>: make -o all bindist             (layout cases) the output of the
                                             recipe run on stand-in build
                                             products, its exit status
  ## <case>: tree bindist/                   the distribution directory: path,
                                             type, mode, size, SHA-256 (12),
                                             mtime (`kept`: the source's, `new`)
  ## <case>: file bindist/Makefile.distcheck

The application is a copy outside the tree (Make's recipe writes into the
application directory), RIOTBASE on the command line. Stand-in build
products: an empty file for every object of the build plan (G3-1; its
objects are Make's, P1 there), the ELF and the binary with fixed content.
Every source file and directory gets mode 0644/0755 and the mtime FIXED, the
recipe runs with umask 022. Paths: @RIOTBASE@, @APPDIR@, @TMP@; the
computed RIOT_VERSION and git describe are masked (they name the checkout).
The file ends with `## end`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLDEN = os.path.join(HERE, "golden")
BOARD = "nrf52840dk"
APP = "bindist"
APP_DIR = "examples/advanced/bindist"
FIXED = 1700000000            # mtime of every source file and directory
UMASK = 0o022
CLI = os.path.join(TOOL, "bindist.py")

# name -> (command line variables, layout case)
CASES = {
    "default": ({}, True),
    "dist-files": ({"DIST_FILES": "Makefile abc/abc.c"}, True),
    "riot-version": ({"RIOT_VERSION": "9.9-test"}, True),
    "bindirbase": ({"BINDIRBASE": "@TMP@/elsewhere"}, False),
    "no-products": ({}, True),
}
NO_PRODUCTS = "no-products"   # the layout run without build products

for _sub in ("cmake_gen", "resolver", "config_data"):
    sys.path.insert(0, os.path.join(TOOL, "..", _sub))


def golden_path() -> str:
    return os.path.join(GOLDEN, f"{APP}__{BOARD}.txt")


def title(case: str, variables: dict, what: str) -> str:
    shown = " ".join(shlex.quote(f"{k}={v}") for k, v in variables.items())
    return f"## {case}: {what} [{APP_DIR}{' ' + shown if shown else ''}]"


def real(variables: dict, tmp: str) -> dict:
    return {k: v.replace("@TMP@", tmp) for k, v in variables.items()}


def make_argv(app_copy: str, riotbase: str, variables: dict, extra: list) -> list:
    return (["make", "--no-print-directory", "-C", app_copy, f"BOARD={BOARD}",
             f"RIOTBASE={riotbase}"] + [f"{k}={v}" for k, v in variables.items()] + extra)


def tool_argv(app_copy: str, variables: dict, extra: list) -> list:
    return ([sys.executable, CLI, "bindist", *extra, "-C", app_copy, f"BOARD={BOARD}",
             f"RIOTBASE={RIOTBASE}"] + [f"{k}={v}" for k, v in variables.items()])


def environment(path: str = None, **extra) -> dict:
    env = {"PATH": path or os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}
    env.update(extra)
    return env


def with_umask():
    os.umask(UMASK)


# --- the application copy and the stand-in build products ---------------------------
def copy_app(riotbase: str, tmp: str) -> str:
    target = os.path.join(tmp, APP)
    shutil.copytree(os.path.join(riotbase, APP_DIR), target, symlinks=True,
                    ignore=shutil.ignore_patterns("bin", "bindist"))
    return target


def products(app_copy: str, bindir: str) -> list:
    """The paths (relative to BINDIR) of the build products of the plan
    (step G3-1): every object, the ELF and the binary."""
    import plan as P  # pylint: disable=import-outside-toplevel
    plan = P.build_plan(app_copy, {"BOARD": BOARD, "RIOTBASE": RIOTBASE, "BINDIR": bindir,
                                   "BUILD_DIR": os.path.join(os.path.dirname(bindir), "build")})
    paths = [o["object"] for m in plan["modules"] for o in m["objects"]]
    paths += [plan["link"]["output"]] + [f["output"] for f in plan["files"]]
    return sorted(os.path.relpath(p, bindir) for p in paths)


def fake_products(bindir: str, names: list):
    for name in names:
        path = os.path.join(bindir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file:
            file.write(f"stand-in {name}\n".encode())


def fix_sources(root: str):
    """Mode 0644/0755 (executables 0755) and mtime FIXED for the tree."""
    for directory, dirs, files in os.walk(root, topdown=False):
        for name in files:
            path = os.path.join(directory, name)
            mode = 0o755 if os.stat(path).st_mode & stat.S_IXUSR else 0o644
            os.chmod(path, mode)
            os.utime(path, (FIXED, FIXED))
        for name in dirs:
            os.chmod(os.path.join(directory, name), 0o755)
            os.utime(os.path.join(directory, name), (FIXED, FIXED))
    os.chmod(root, 0o755)
    os.utime(root, (FIXED, FIXED))


def prepare(riotbase: str, tmp: str, case: str) -> str:
    """The application copy with Make's BINDIR (bin/<board>) holding the
    stand-in products (none for NO_PRODUCTS); sources fixed."""
    app_copy = copy_app(riotbase, tmp)
    bindir = os.path.join(app_copy, "bin", BOARD)
    if case != NO_PRODUCTS:
        fake_products(bindir, products(app_copy, bindir))
    fix_sources(app_copy)
    return app_copy


# --- what is compared ----------------------------------------------------------------
OWN_SECTION = ("Makefile.distcheck",)   # its content names the checkout


def tree(directory: str) -> list:
    """One line per entry of the directory (sorted, C locale)."""
    out = []
    if not os.path.isdir(directory):
        return ["(no directory)"]
    entries = []
    for root, dirs, files in os.walk(directory):
        entries += [os.path.join(root, n) for n in dirs + files]
    for path in sorted(entries, key=lambda p: os.path.relpath(p, directory).encode()):
        st = os.lstat(path)
        kind = "dir" if stat.S_ISDIR(st.st_mode) else "link" if stat.S_ISLNK(st.st_mode) \
            else "file"
        mtime = "kept" if int(st.st_mtime) == FIXED else "new"
        line = f"{os.path.relpath(path, directory)} {kind} {stat.S_IMODE(st.st_mode):04o}"
        if kind == "file" and os.path.basename(path) in OWN_SECTION:
            line += " (content: own section)"
        elif kind == "file":
            with open(path, "rb") as file:
                digest = hashlib.sha256(file.read()).hexdigest()[:12]
            line += f" {st.st_size} {digest}"
        out.append(f"{line} mtime={mtime}")
    return out


def read(path: str) -> list:
    if not os.path.exists(path):
        return ["(no file)"]
    with open(path, encoding="utf-8") as file:
        return file.read().rstrip("\n").split("\n")


VERSION_RE = re.compile(r"(BINDIST_RIOT_VERSION=)[^\"\n]*")
DESCRIBE_RE = re.compile(r"^(BINDIST_GIT_HEAD=).*$", re.M)
MAKE_ERROR_RE = re.compile(r"^make: \*\*\* .*$")


def normalise(text: str, pairs: list, variables: dict) -> str:
    for path, name in sorted(pairs, key=lambda p: -len(p[0])):
        text = text.replace(path, name)
    if "RIOT_VERSION" not in variables:
        text = VERSION_RE.sub(r"\1@RIOT_VERSION@", text)
    return DESCRIBE_RE.sub(r"\1@GIT_DESCRIBE@", text)


def without_make_messages(lines: list) -> list:
    """The output of the recipe without Make's own error line."""
    return [line for line in lines if not MAKE_ERROR_RE.match(line)]


# --- golden files ------------------------------------------------------------------
def read_golden(path: str = None) -> tuple:
    """(header lines, {section title: [lines]}); `## exit:` stays in the body."""
    with open(path or golden_path(), encoding="utf-8") as file:
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


def exit_and_lines(body: list) -> tuple:
    status = int(body[0].split(":", 1)[1]) if body and body[0].startswith("## exit:") else None
    return status, [line for line in body[1:] if line] if status is not None else body


# --- one run ---------------------------------------------------------------------------
DRY = "make -n -o all bindist"
RUN = "make -o all bindist"
TREE = "tree bindist/"
DISTCHECK = "file bindist/Makefile.distcheck"


def sections_of(case: str, variables: dict, dry: tuple, run: tuple = None,
                app_copy: str = None, pairs: list = ()) -> list:
    """The golden lines of one case: dry = (status, text), run = (status, text)."""
    out = [title(case, variables, DRY), f"## exit: {dry[0]}",
           normalise(dry[1], pairs, variables)]
    if run is not None:
        out += [title(case, variables, RUN), f"## exit: {run[0]}",
                normalise(run[1], pairs, variables),
                title(case, variables, TREE)] + tree(os.path.join(app_copy, "bindist"))
        out += [title(case, variables, DISTCHECK)] + [
            normalise(line, pairs, variables)
            for line in read(os.path.join(app_copy, "bindist", "Makefile.distcheck"))]
    return out


def run(argv: list, env: dict = None) -> tuple:
    import subprocess  # pylint: disable=import-outside-toplevel
    res = subprocess.run(argv, cwd=RIOTBASE, env=env or environment(), capture_output=True,
                         text=True, check=False, preexec_fn=with_umask)
    return res.returncode, (res.stdout + res.stderr).rstrip("\n")


def run_case(case: str, tmp: str, make_root: str = None) -> list:
    """The golden lines of one case, from Make (make_root: the RIOT tree Make
    runs in) or from the bindist without Make (make_root None)."""
    variables, layout = CASES[case]
    riotbase = make_root or RIOTBASE
    app_copy = prepare(riotbase, tmp, case)
    values = real(variables, tmp)
    if make_root:
        argv = lambda extra: make_argv(app_copy, make_root, values, extra)  # noqa: E731
        dry, go = ["-n", "-o", "all", "bindist"], ["-o", "all", "bindist"]
    else:
        argv = lambda extra: tool_argv(app_copy, values, extra)  # noqa: E731
        dry, go = ["-n"], ["--no-build"]
    pairs = [(riotbase, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
    dry_result = run(argv(dry))
    run_result = run(argv(go)) if layout else None
    return sections_of(case, variables, dry_result, run_result, app_copy, pairs)
