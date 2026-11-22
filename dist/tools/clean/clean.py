#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Remove the build products of an application without Make, from data only
(step G2C-1).

  clean.py clean -C <app> BOARD=<board> [-B <dir>] [-n] [VAR=VALUE…]
      remove what GNU Make's target `clean` removes (the package build
      directories, Make's BINDIR, the scan-build reports) and the build
      directory of `just build`/`just flash` (default <app>/bin/cmake-<board>,
      or <dir>). -n: print the commands, run nothing
  clean.py generate [--check] [CLEAN_DATA…]
      write (check) the Make adapters generated from the clean data (all
      clean data files of the repository without arguments)

Inputs: the YAML data of the repository (resolver G0-2, build data G3-1,
package data, clean data `<x>.clean.yaml`, see cleandata.py). Nothing here
runs make, opens a Make file or parses Make syntax. Exit status: 0 (a
failing command is ignored, as Make's `-`); 2 an error of the configuration;
3 the request is outside the data; 4 a path outside the application's build
directories and RIOT's build directory: refused, nothing removed.

What is algorithm (this file) and what it replaces (Make file:line):

  CleanEvaluator   the clean data is read where Make includes its owner
                   (makefiles/scan-build.inc.mk at Makefile.include:211)
  make_part        Makefile.include:605-611 (`clean`): one sub-make per
                   package of PKG_PATHS, rm -rf BINDIR, rm -rf
                   SCANBUILD_OUTPUTDIR (in the application directory)
  package_part     pkg/pkg.mk:178-185 (`clean::` of every package): rm -rf
                   PKG_BUILD_DIR, or `git clean` in PKG_SOURCE_DIR when the
                   package builds in its source directory
  build_part       the build directory of `just build`/`just flash`
                   (cmake_gen.py builddir()), which Make does not know
  refusals         safety: what may be removed (rules S1-S5, README)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import cleandata as D  # noqa: E402  (sets up the import path)
import buildeval  # noqa: E402
import cmake_gen  # noqa: E402
import pipeline  # noqa: E402
import plan as P  # noqa: E402
import resolver  # noqa: E402
from buildeval import OutOfScope, ResolveError, rel, RIOTBASE  # noqa: E402

REFUSED = 4
# Make files whose clean part is data, where Makefile.include includes them
CLEAN_OWNERS = (("makefiles/scan-build.inc.mk", "Makefile.include:211"),)
# pkg/pkg.mk: PKG_STATE_FILE (the state files `git clean` keeps)
PKG_STATE_FILE = ".pkg-state.git"
# S1: a path is one plain word of these characters (no blank, quote, glob,
# variable or command substitution: the shell would see what Make passes)
PLAIN = re.compile(r"[A-Za-z0-9_./+,@%=:-]+")


class CleanEvaluator(buildeval.BuildEvaluator):
    """The build evaluator of G3-1 that also reads the clean data."""

    def __init__(self, variables, curdir: str):
        super().__init__(variables, curdir)
        self.clean_read: list = []

    def load(self, yaml_path: str) -> list:
        if not D.is_data_name(yaml_path):
            return super().load(yaml_path)
        try:
            rules = D.load(yaml_path)
        except ValueError as err:
            raise ResolveError(str(err)) from None
        self.read.append(rel(yaml_path))
        self.clean_read.append(rel(yaml_path))
        return rules

    def clean_part(self, owner: str):
        """The clean data of a Make file (the include of its adapter, the
        first statement of the Make file)."""
        data = D.data_name(os.path.join(RIOTBASE, owner))
        if not os.path.isfile(data):
            raise ResolveError(f"{rel(data)}: no such file (clean data of {owner})")
        self.run_file(data)


def check_scope(v):
    """Requests whose clean is not in the data."""
    local = [n for n in v.names() if n == "PKG_SOURCE_LOCAL" or n.startswith("PKG_SOURCE_LOCAL_")]
    if any(v.get(n).strip() for n in local):
        raise OutOfScope("PKG_SOURCE_LOCAL: the clean of pkg/local.mk is not converted to data")


def evaluate(app_dir: str, variables: dict) -> CleanEvaluator:
    """The variables of Make's top level for `clean`."""
    v = buildeval.BuildVariables(P.PROVIDERS)
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = CleanEvaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)

    def build_system():
        pipeline.prelude(ev)
        pipeline.application(ev, info_goal=False)
        P.directories(v)
        for owner, _ in CLEAN_OWNERS:
            ev.clean_part(owner)
        ev.run_file(os.path.join(RIOTBASE, "makefiles", "pseudomodules.build.yaml"))
        ev.run_file(os.path.join(RIOTBASE, "build.yaml"))
    resolver._run_application(ev, build_system)   # pylint: disable=protected-access
    check_scope(v)
    return ev


# --- the plan: one entry per command --------------------------------------------------
def rm_entry(path: str, cwd: str, origin: str, echo: bool, package: str = None) -> dict:
    return {"command": f"rm -rf {path}", "argv": ["rm", "-rf", path], "cwd": cwd,
            "targets": [path], "test_dir": None, "echo": echo, "origin": origin,
            "package": package}


def git_clean_entry(src: str, cwd: str, package: str) -> dict:
    git = ["git", "-C", src, "--git-dir=.git", "--work-tree=."]
    return {"command": f"test -d {src} && {' '.join(git)} clean -xdff '**' "
                       f"-e '{PKG_STATE_FILE}*'",
            "argv": git + ["clean", "-xdff", "**", "-e", f"{PKG_STATE_FILE}*"], "cwd": cwd,
            "targets": [src], "test_dir": src, "echo": False, "origin": "pkg/pkg.mk:181",
            "package": package}


def package_part(env: dict, cmdline: dict, pkg_path: str, read: list) -> list:
    """`make -C <pkg> clean` (Makefile.include:607): the `clean::` rule of
    pkg/pkg.mk:178-185 with the package's variables."""
    curdir = os.path.normpath(pkg_path)
    make_file = os.path.join(curdir, "Makefile")
    data = buildeval.pkg_yaml_name(make_file)
    if not os.path.isfile(data):
        raise OutOfScope(f"{rel(make_file)} is not converted to package data "
                         f"({rel(data)} is missing)")
    v = P.child(env, cmdline, curdir)
    ev = buildeval.BuildEvaluator(v, curdir)
    ev.run_file(data)
    read.extend(ev.read)
    src, build = v.get("PKG_SOURCE_DIR").strip(), v.get("PKG_BUILD_DIR").strip()
    if src == build:
        # `@-test -d … && git … clean`: silent
        return [git_clean_entry(src, curdir, pkg_path)]
    # `rm -rf $(PKG_BUILD_DIR)`: no `@`, Make prints it
    return [rm_entry(build, curdir, "pkg/pkg.mk:184", True, pkg_path)]


def make_part(ev) -> list:
    """Makefile.include:605-611, in Make's order."""
    v = ev.v
    names = v.words("BUILD_EXPORTED")
    env, cmdline = P.exported(v, names), P.command_line(v)
    curdir = v.get("CURDIR").strip()
    entries = []
    for pkg_path in v.words("PKG_PATHS"):
        entries += package_part(env, cmdline, pkg_path, ev.read)
    entries.append(rm_entry(v.get("BINDIR").strip(), curdir, "Makefile.include:608", False))
    entries.append(rm_entry(v.get("SCANBUILD_OUTPUTDIR").strip(), curdir,
                            "Makefile.include:609", False))
    return entries


def inside(path: str, root: str, strict: bool = True) -> bool:
    if os.path.commonpath([path, root]) != root:
        return False
    return path != root or not strict


def build_part(app_dir: str, variables: dict, builddir: str, bindir: str) -> list:
    """The build directory of `just build`/`just flash` (cmake_gen.py
    builddir()); nothing when it is Make's BINDIR or inside it (`just
    bindist` builds there)."""
    directory = cmake_gen.builddir(argparse.Namespace(app=app_dir, builddir=builddir),
                                   variables)
    if inside(directory, bindir, strict=False):
        return []
    return [rm_entry(directory, os.path.abspath(app_dir), "cmake_gen.py builddir()", False)]


def roots(v) -> list:
    """The application's build directories and RIOT's build directory: the
    only directories below which `clean` removes anything (S2). A root that
    is `/`, the home directory, RIOTBASE, the application directory or a
    directory above one of them is no root."""
    get = lambda name: os.path.normpath(v.get(name).strip())  # noqa: E731
    protected = {"/", os.path.normpath(os.path.expanduser("~")), RIOTBASE, get("APPDIR"),
                 get("CURDIR")}
    protected |= {os.path.realpath(p) for p in protected}
    candidates = [os.path.join(get("APPDIR"), "bin"), get("BINDIRBASE"),
                  os.path.join(get("CURDIR"), "scan-build"), get("BUILD_DIR")]
    found = []
    for root in candidates:
        if not os.path.isabs(root) or root in found:
            continue
        if any(inside(p, root, strict=False) or inside(p, os.path.realpath(root), strict=False)
               for p in protected):
            continue
        found.append(root)
    return found


def plan_clean(app_dir: str, variables: dict, builddir: str = None) -> dict:
    """What `make clean` does, and the build directory of the build without
    Make."""
    ev = evaluate(app_dir, variables)
    v = ev.v
    recipe = make_part(ev)
    build = build_part(app_dir, variables, builddir, v.get("BINDIR").strip())
    return {"clean": recipe, "build": build, "curdir": v.get("CURDIR").strip(),
            "roots": roots(v), "packages": v.words("PKG_PATHS"), "data": ev.clean_read}


def refusals(result: dict) -> list:
    """S1-S4 for every path of the plan (empty: everything may be removed)."""
    problems = []
    real_roots = [(r, os.path.realpath(r)) for r in result["roots"]]
    for entry in result["clean"] + result["build"]:
        for target in entry["targets"]:
            if not PLAIN.fullmatch(target) or ".." in target.split("/"):
                problems.append(f"{target!r}: not a plain path (S1)")
                continue
            path = os.path.normpath(os.path.join(entry["cwd"], target))
            root = next((r for r, _ in real_roots if inside(path, r)), None)
            if root is None:
                problems.append(f"{path}: outside the application's build directories and "
                                f"RIOT's build directory (S2: {' '.join(result['roots'])})")
                continue
            parent = os.path.realpath(os.path.dirname(path))
            if not inside(parent, os.path.realpath(root), strict=False):
                problems.append(f"{path}: leaves {root} through a symbolic link (S3)")
    return problems


def run(result: dict) -> int:
    """Run the plan as Make runs `clean`: every line, a failure ignored."""
    for entry in result["clean"] + result["build"]:
        if entry["test_dir"] is not None and not os.path.isdir(entry["test_dir"]):
            continue                       # `test -d … &&`: nothing to clean
        if entry["echo"]:
            print(entry["command"], flush=True)
        status = subprocess.run(entry["argv"], cwd=entry["cwd"], check=False).returncode
        if status != 0:
            print(f"clean: `{entry['command']}` ({entry['origin']}) failed with exit status "
                  f"{status} (ignored, as Make's `-`)", file=sys.stderr)
    return 0


# --- command line ---------------------------------------------------------------------
def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("clean", "generate"))
    parser.add_argument("-C", dest="app", help="application directory")
    parser.add_argument("-B", dest="builddir", help="build directory of `just build`")
    parser.add_argument("-n", "--dry-run", action="store_true", help="print, run nothing")
    parser.add_argument("--check", action="store_true", help="generate: only check")
    parser.add_argument("variables", nargs="*", metavar="VAR=VALUE|FILE")
    args = parser.parse_intermixed_args(argv)
    variables = {}
    if args.command == "generate":
        return args, variables
    for item in args.variables:
        if "=" not in item:
            parser.error(f"not a variable: {item}")
        name, value = item.split("=", 1)
        variables[name] = value
    if not args.app or "BOARD" not in variables:
        parser.error("clean needs -C <application> and BOARD=<board>")
    return args, variables


def cmd_generate(check: bool, files: list = None) -> int:
    stale = 0
    for path in files or D.all_data():
        target = D.adapter_name(path)
        try:
            text = D.expected_adapter(path)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            stale += 1
            continue
        current = None
        if os.path.exists(target):
            with open(target, encoding="utf-8") as file:
                current = file.read()
        if current == text:
            continue
        if check:
            print(f"{rel(target)} is not up to date with {os.path.basename(path)}",
                  file=sys.stderr)
            stale += 1
        else:
            with open(target, "w", encoding="utf-8") as file:
                file.write(text)
            print(f"wrote {rel(target)}")
    if stale and check:
        print("Change the clean data, never the adapter; run `just generate-clean-data`.",
              file=sys.stderr)
    return 1 if stale else 0


def cmd_clean(args, variables: dict) -> int:
    result = plan_clean(args.app, variables, args.builddir)
    problems = refusals(result)
    if problems:
        for problem in problems:
            print(f"refused: {problem}", file=sys.stderr)
        print("Nothing removed.", file=sys.stderr)
        return REFUSED
    if args.dry_run:
        for entry in result["clean"] + result["build"]:
            print(entry["command"])
        return 0
    return run(result)


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "generate":
            return cmd_generate(args.check, [os.path.abspath(f) for f in args.variables])
        return cmd_clean(args, variables)
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
