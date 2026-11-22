# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G2C-2 (distclean without Make) and the golden file of GNU
Make. Built on the sample of step G2C-1 (dist/tools/clean/tests/sample.py:
application copies, stub toolchain, stand-in packages, tree listing,
normalisation), which it imports instead of repeating.

The golden file holds:

  ## <case>: make -n distclean [<app> VAR=VALUE…]   the commands of the
                                                   application's distclean
                                                   for every case (CASES)
  ## <tree>: build products before make distclean  files per build directory
  ## <tree>: make distclean (after make <goal>)     output and exit status of
                                                   `make distclean` in an
                                                   application copy that
                                                   Make built (TREES)
  ## <tree>: tree after make distclean              every path left in the
                                                   temporary directory

Before `distclean` the copy gets the stand-ins of sample.EXTRA (other
boards' build directories, scan-build reports) and BUILD_DIR the stand-ins of
KEEP_IN_BUILD_DIR (another package's sources, which distclean keeps). The
tree `hello-world-locked` adds a directory that `rm -rf` cannot empty
(LOCKED, mode 0555) below the build directory of pkg/cmsis: Make's package
sub-make stops at its first failing line, the top level ignores it. Paths:
@RIOTBASE@, @APPDIR@, @TMP@. The file ends with `## end`.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN_TESTS = os.path.normpath(os.path.join(HERE, "..", "..", "clean", "tests"))
sys.path.insert(0, CLEAN_TESTS)

# pylint: disable=wrong-import-position
import sample as S  # noqa: E402  (the G2C-1 sample: also sets up the import path)

RIOTBASE, BOARD, APPS = S.RIOTBASE, S.BOARD, S.APPS
CLI = S.CLI
GOLDEN = os.path.join(HERE, "golden")
# name -> (application, command line variables)
CASES = {
    "hello-world": ("hello-world", {}),
    "gnrc_networking": ("gnrc_networking", {}),
    "bindist": ("bindist", {}),
    "bindirbase": ("hello-world", {"BINDIRBASE": "@TMP@/elsewhere"}),
    "pkgdirbase": ("hello-world", {"PKGDIRBASE": "@TMP@/pkg"}),
    "build-dir": ("hello-world", {"BUILD_DIR": "@TMP@/build"}),
    "in-source-packages": ("hello-world", {"PKG_BUILD_OUT_OF_SOURCE": "0"}),
    "docker": ("hello-world", {"BUILD_IN_DOCKER": "1"}),
}
# tree -> application (the build goal: sample.GOALS)
TREES = {"hello-world": "hello-world", "gnrc_networking": "gnrc_networking",
         "bindist": "bindist", "hello-world-locked": "hello-world"}
KEEP_IN_BUILD_DIR = ("pkg/other-package/.pkg-state.git-prepared", "pkg/other-package/x.c")
LOCKED = f"bin/{BOARD}/pkg-build/cmsis/locked"


def golden_path() -> str:
    return os.path.join(GOLDEN, f"distclean__{BOARD}.txt")


def dry_title(case: str) -> str:
    app, variables = CASES[case]
    extra = S.shown(variables)
    return f"## {case}: make -n distclean [{APPS[app]}{' ' + extra if extra else ''}]"


def goal(tree: str) -> str:
    return S.GOALS[TREES[tree]]


def products_title(tree: str) -> str:
    return f"## {tree}: build products before make distclean (after make {goal(tree)})"


def output_title(tree: str) -> str:
    return f"## {tree}: make distclean (after make {goal(tree)})"


def tree_title(tree: str) -> str:
    return f"## {tree}: tree after make distclean"


def tool_argv(app_copy: str, variables: dict, extra: list) -> list:
    return ([sys.executable, CLI, "distclean", *extra, "-C", app_copy, f"BOARD={BOARD}",
             f"RIOTBASE={RIOTBASE}"] + [f"{k}={v}" for k, v in variables.items()])


SUBMAKE_RE = re.compile(r'^"make" -C (\S+) distclean ?$')


def commands(lines: list) -> list:
    """`make -n distclean` lines -> [(package directory or None, command)]:
    the sub-make line of a package (Makefile.include:625) names the package
    of the commands after it; the last line (rm -rf BINDIRBASE,
    Makefile.include:626) is the top level's."""
    out, package = [], None
    for line in lines:
        match = SUBMAKE_RE.match(line)
        if match:
            package = match.group(1)
            continue
        out.append((package, line))
    return [(p if i < len(out) - 1 else None, c) for i, (p, c) in enumerate(out)]


def plan_commands(result: dict, pairs: list) -> list:
    return [(S.normalise(e["package"], pairs) if e["package"] else None,
             S.normalise(e["command"], pairs)) for e in result["clean"]]


def read_golden(path: str = None) -> tuple:
    return S.read_golden(path or golden_path())


def dry_case(case: str, tmp: str, make_root: str = None) -> tuple:
    """(status, normalised lines) of `make -n distclean` (make_root: the RIOT
    tree Make runs in) or `clean.py distclean -n` (make_root None)."""
    app, variables = CASES[case]
    riotbase = make_root or RIOTBASE
    app_copy = S.copy_app(riotbase, tmp, app)
    values = S.real(variables, tmp)
    argv = S.make_argv(app_copy, make_root, values, ["-n", "distclean"]) if make_root else \
        tool_argv(app_copy, values, ["-n"])
    status, text = S.run(argv)
    pairs = [(riotbase, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
    return status, S.normalise(text, pairs).split("\n") if text else []


def stand_ins(tree: str, app_copy: str, build_dir: str):
    """What distclean must remove or keep, put in before it runs."""
    S.extra_stand_ins(app_copy)
    for name in KEEP_IN_BUILD_DIR:
        S._touch(os.path.join(build_dir, name), 0)  # pylint: disable=protected-access
    if tree.endswith("-locked"):
        S._touch(os.path.join(app_copy, LOCKED, "keep.o"), 0)  # pylint: disable=protected-access
        os.chmod(os.path.join(app_copy, LOCKED), 0o555)


def unlock(app_copy: str):
    """Make the locked directory removable again (before the temporary
    directory is removed)."""
    path = os.path.join(app_copy, LOCKED)
    if os.path.isdir(path):
        os.chmod(path, 0o755)


def make_build_and_distclean(tree: str, tmp: str, make_root: str) -> list:
    """The golden sections of a tree case, from Make."""
    app = TREES[tree]
    app_copy, build_dir, path = S.built_tree(app, tmp, make_root)
    env = S.environment(path)
    argv = lambda extra: S.make_argv(app_copy, make_root, {"BUILD_DIR": build_dir},  # noqa: E731
                                     extra)
    status, text = S.run(argv(["-j1", S.GOALS[app]]), env)
    if status != 0:
        raise RuntimeError(f"make {S.GOALS[app]} failed:\n{text[-3000:]}")
    products = [products_title(tree)] + S.count_products(app_copy)
    stand_ins(tree, app_copy, build_dir)
    try:
        status, text = S.run(argv(["distclean"]), env)
        left = S.tree(tmp)
    finally:
        unlock(app_copy)
    pairs = [(make_root, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
    return products + [output_title(tree), f"## exit: {status}", S.normalise(text, pairs),
                       tree_title(tree)] + left


# Make's own messages (`make: …`, `make[1]: …`) and those of clean.py
# (`distclean: …`) for a failing line; everything else (the printed
# commands, rm's messages) must be the same
DIAGNOSTIC_RE = re.compile(r"^(make(\[\d+\])?|distclean): ")


def without_diagnostics(lines: list) -> list:
    return [line for line in lines if line and not DIAGNOSTIC_RE.match(line)]


# --- an application copy for the unit tests -------------------------------------------
def variables(**extra) -> dict:
    return dict({"BOARD": BOARD, "RIOTBASE": RIOTBASE}, **extra)


class Tree:
    """An application copy and a BUILD_DIR in a temporary directory, with
    stand-ins of what distclean removes and keeps."""

    REMOVED = (f"bin/{BOARD}/core/x.o", f"bin/{BOARD}/pkg-build/cmsis/y.o",
               f"bin/cmake-{BOARD}/build.ninja", "bin/native64/z.o",
               "bin/cmake-native64/build.ninja")
    KEPT = (f"scan-build/{BOARD}/index.html", "bindist/hello-world.elf", "main.c",
            "Makefile", "riot-app.yaml")
    REMOVED_IN_BUILD_DIR = ("pkg/cmsis/.pkg-state.git-prepared", "pkg/cmsis/CMSIS/x.h",
                            "pkg/mpaland-printf/printf.c")
    KEPT_IN_BUILD_DIR = ("pkg/cmsis.sparse", "pkg/other/x.c", "CACHEDIR.TAG",
                         "nrf5x_nrfx_mdk/nrf52/mdk/nrf52.h")

    def __init__(self, app="hello-world"):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2c2-tree-")
        self.root = self.tmp.name
        self.app = S.copy_app(RIOTBASE, self.root, app)
        self.build = os.path.join(self.root, "build")
        for name in self.REMOVED + self.KEPT[:2]:
            self.put(name)
        for name in self.REMOVED_IN_BUILD_DIR + self.KEPT_IN_BUILD_DIR:
            self.put(name, self.build)

    def put(self, name: str, base: str = None):
        path = os.path.join(base or self.app, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write("stand-in\n")
        return path

    def exists(self, name: str, base: str = None) -> bool:
        return os.path.lexists(os.path.join(base or self.app, name))

    def distclean(self, *args, **values):
        """(exit status, stdout, stderr) of clean.py distclean, in this process."""
        out, err = io.StringIO(), io.StringIO()
        values = variables(**dict({"BUILD_DIR": self.build}, **values))
        argv = ["distclean", "-C", self.app] + list(args) + \
            [f"{k}={v}" for k, v in values.items()]
        import clean  # pylint: disable=import-outside-toplevel
        with redirect_stdout(out), redirect_stderr(err):
            status = clean.main(argv)
        return status, out.getvalue(), err.getvalue()

    def assert_untouched(self, case):
        for name in self.REMOVED + self.KEPT:
            case.assertTrue(self.exists(name), name)
        for name in self.REMOVED_IN_BUILD_DIR + self.KEPT_IN_BUILD_DIR:
            case.assertTrue(self.exists(name, self.build), name)

    def cleanup(self):
        self.tmp.cleanup()
