#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""The package step of the build without Make (step G3-1).

Fetches, patches and prepares a package as the recipes of pkg/pkg.mk do
(and copies files as cpu/nrf5x_common/Makefile.nrfx does), with the same
git commands and the same state files in the package directory:

  <source_dir>.sparse            sparse paths (rewritten when they change)
  <source_dir>/.git              clone: init, sparse checkout, fetch, checkout
  .pkg-state.git-downloaded      the version is there (fetched if missing)
  .pkg-state.git-patched         clean checkout of the version + the patches
  .pkg-state.git-prepared        done

A state file is remade when it is missing or older than one of its inputs
(Make's rule): `downloaded` after the package data files, `patched` after
`downloaded` and the patches. Make also remakes them when one of its Make
files changes; here the package data files take that place.

Input: one package of the plan (JSON, plan.py). Every command is printed
before it runs (`--dry-run`: printed only).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

STATE = ".pkg-state.git"


class PackageError(Exception):
    """A command of the package step failed."""


class Runner:
    """Prints and runs shell commands (as Make runs recipe lines)."""

    def __init__(self, dry_run: bool = False, log=None, verbose: bool = True):
        self.dry_run = dry_run
        self.log = log if log is not None else []
        self.verbose = verbose

    def run(self, command: str, check: bool = True) -> int:
        self.log.append(command)
        if self.verbose:
            print(command, flush=True)
        if self.dry_run:
            return 0
        status = subprocess.run(["/bin/sh", "-c", command], check=False,
                                stdout=None if self.verbose else subprocess.DEVNULL,
                                stderr=None if self.verbose else subprocess.DEVNULL).returncode
        if check and status != 0:
            raise PackageError(f"command failed ({status}): {command}")
        return status


def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return -1.0


def _outdated(target: str, inputs: list) -> bool:
    if not os.path.exists(target):
        return True
    return any(_mtime(i) > _mtime(target) for i in inputs)


def prepare(spec: dict, riotbase: str, runner: Runner = None) -> list:
    """Bring the package of `spec` to the prepared state; returns the
    commands run."""
    runner = runner or Runner()
    src = spec["source_dir"]
    q = spec["git_quiet"]
    git = f"git -C {src} --git-dir=.git --work-tree=."
    qarg = f" {q}" if q else ""
    data = [os.path.join(riotbase, p) for p in spec["data"]]
    version = spec["version"]
    sparse = spec["sparse_paths"]
    # the step writes and removes only inside BUILD_DIR
    build_dir = os.path.abspath(spec["build_dir"])
    if os.path.commonpath([os.path.abspath(src), build_dir]) != build_dir or \
            os.path.abspath(src) == build_dir:
        raise PackageError(f"refusing to prepare {src}: not inside {spec['build_dir']}")
    # pkg.mk:173-178: the sparse tag file (always checked)
    tag_changed = False
    if sparse:
        tag = f"{src}.sparse"
        current = None
        if os.path.exists(tag):
            with open(tag, encoding="utf-8") as file:
                current = file.read().strip()
        if current != " ".join(sparse):
            runner.run(f"mkdir -p $(dirname {tag}) && echo \"{' '.join(sparse)}\" > {tag}")
            tag_changed = True
    # pkg.mk:186-205: clone
    if not os.path.isdir(os.path.join(src, ".git")) or tag_changed:
        runner.run(f"rm -Rf {src}")
        runner.run(f"mkdir -p {src}")
        runner.run(f"git init{qarg} {src}")
        if sparse:
            runner.run(f"{git} sparse-checkout init --no-cone")
            paths = " ".join(f'"{p}"' for p in sparse)
            runner.run(f"{git} sparse-checkout set -- {paths}")
        runner.run(f"{git} remote add origin {spec['url']}")
        runner.run(f"{git} config remote.origin.promisor true")
        runner.run(f"{git} config remote.origin.partialclonefilter blob:none")
        runner.run(f"{git} config advice.detachedHead false")
        runner.run(f"{git} fetch{qarg} --depth=1 -t --filter=blob:none origin {version}")
        runner.run(f"{git} checkout{qarg} {version} 2>&1 | cat")
    downloaded = os.path.join(src, STATE + "-downloaded")
    patched = os.path.join(src, STATE + "-patched")
    prepared = os.path.join(src, STATE + "-prepared")
    # pkg.mk:160-166
    # (.git is an order-only prerequisite of the downloaded state)
    if _outdated(downloaded, data) or runner.dry_run:
        if runner.run(f"{git} cat-file -e {version}", check=False) != 0:
            runner.run(f'{git} fetch{qarg} "{spec["url"]}" "{version}"')
        runner.run(f"echo {version} > {downloaded}")
    # pkg.mk:143-158
    if _outdated(patched, spec["patches"] + [downloaded] + data) or runner.dry_run:
        runner.run(f"{git} clean{qarg} -xdff '**' -e '{STATE}*'")
        runner.run(f"{git} checkout{qarg} -f {version}")
        if spec["patches"]:
            patches = " ".join(spec["patches"])
            if spec["ci"]:
                runner.run(f"{git} apply --index --ignore-whitespace --whitespace=nowarn "
                           f"{patches}")
            else:
                runner.run(f"{git} {spec['gitflags']} am {spec['gitamflags']} {patches}")
        runner.run(f"touch {patched}")
    # Makefile.nrfx:74-84: files copied after patching
    copy = spec.get("copy")
    if copy:
        for name in copy["files"]:
            target = os.path.join(copy["to"], name)
            if _outdated(target, [patched]) or runner.dry_run:
                runner.run(f"mkdir -p {copy['to']}")
                runner.run(f"cp {os.path.join(copy['from'], name)} {target}")
    # pkg.mk:126-128 (BUILD_DIR/CACHEDIR.TAG, an order-only prerequisite)
    tag_file = os.path.join(spec["build_dir"], "CACHEDIR.TAG")
    if not os.path.exists(tag_file):
        runner.run(f'mkdir -p "{spec["build_dir"]}"')
        runner.run(f'echo "Signature: 8a477f597d28d172789f06886806bc55" > "{tag_file}"')
        runner.run(f"echo \"# This folder contains RIOT's build cache\" >> \"{tag_file}\"")
    if _outdated(prepared, [patched]) or runner.dry_run:
        runner.run(f"touch {prepared}")
    return runner.log


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", help="plan.json of cmake_gen.py")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with open(args.plan, encoding="utf-8") as file:
        plan = json.load(file)
    if shutil.which("git") is None:
        print("error: git is required for the packages", file=sys.stderr)
        return 1
    try:
        for spec in plan["packages"]:
            prepare(spec, plan["riotbase"], Runner(args.dry_run))
    except PackageError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
