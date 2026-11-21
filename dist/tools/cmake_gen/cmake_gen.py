#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Build a RIOT application with CMake and Ninja, from data only (step G3-1).

  cmake_gen.py build -C <app> BOARD=<board> [-B <dir>] [-j N] [VAR=VALUE…]
      generate the CMake project, configure it with the Ninja generator in
      the build directory <dir> (default <app>/bin/cmake-<board>) and build
      (the target `all` of Make: ELF, binary, size)
  cmake_gen.py generate -C <app> BOARD=<board> [-B <dir>] [VAR=VALUE…]
      only write <dir>/project/CMakeLists.txt
  cmake_gen.py plan -C <app> BOARD=<board> BINDIR=<dir> [VAR=VALUE…]
      [--cmake FILE] [--json FILE] [--no-packages]
      the build plan (run by CMake at configure time): prepares the packages,
      writes riot-build.cmake, plan.json and compile_commands.json

Inputs: the YAML data of the repository (resolver of G0-2, build data,
module data, package data) and the toolchain probes. Nothing here runs or
reads make or a Make file. VAR=VALUE are command line variables as for
make (e.g. BUILD_DIR=…, WERROR=0). Exit status: 0; 1 usage or a failed
command; 2 an error of the configuration; 3 the request is outside the data.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import emit  # noqa: E402
import pkg_prepare  # noqa: E402
import plan as P  # noqa: E402
from buildeval import OutOfScope, ResolveError, RIOTBASE  # noqa: E402


def parse(argv: list):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "generate", "plan"))
    parser.add_argument("-C", dest="app", required=True, help="application directory")
    parser.add_argument("-B", dest="builddir", help="build directory")
    parser.add_argument("-j", dest="jobs", type=int, default=2, help="parallel jobs (build)")
    parser.add_argument("--cmake", help="plan: write the CMake code to this file")
    parser.add_argument("--json", help="plan: write the plan to this file")
    parser.add_argument("--no-packages", action="store_true",
                        help="plan: do not prepare the packages (they must exist)")
    parser.add_argument("variables", nargs="*", metavar="VAR=VALUE")
    args = parser.parse_intermixed_args(argv)
    variables = {}
    for item in args.variables:
        if "=" not in item:
            parser.error(f"not a variable: {item}")
        name, value = item.split("=", 1)
        variables[name] = value
    if "BOARD" not in variables:
        parser.error("BOARD=<board> is required")
    return args, variables


def builddir(args, variables: dict) -> str:
    return os.path.abspath(args.builddir or os.path.join(
        args.app, "bin", f"cmake-{variables['BOARD']}"))


def cmd_plan(args, variables: dict) -> int:
    if "BINDIR" not in variables:
        print("error: plan needs BINDIR=<build directory>", file=sys.stderr)
        return 1

    def prepare(spec):
        if not args.no_packages:
            pkg_prepare.prepare(spec, RIOTBASE)
    result = P.build_plan(args.app, variables, prepare)
    out_dir = os.path.dirname(os.path.abspath(args.cmake or args.json or
                                              os.path.join(variables["BINDIR"], "x")))
    os.makedirs(out_dir, exist_ok=True)
    data = [os.path.join(RIOTBASE, p) for p in result["data_files"]]
    data += [p for spec in result["packages"] for p in spec["patches"]]
    if args.cmake:
        with open(args.cmake, "w", encoding="utf-8") as file:
            file.write(emit.cmake_text(result, sorted(set(data))))
    with open(args.json or os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as file:
        json.dump(result, file, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, "compile_commands.json"), "w", encoding="utf-8") as file:
        json.dump(P.compile_commands(result), file, indent=1)
    return 0


def cmd_generate(args, variables: dict) -> str:
    directory = builddir(args, variables)
    project = os.path.join(directory, "project")
    os.makedirs(project, exist_ok=True)
    variables = {k: v for k, v in variables.items() if k != "BINDIR"}
    name = "riot_" + "".join(c if c.isalnum() else "_" for c in
                             os.path.basename(os.path.abspath(args.app)))
    text = emit.project_text(name, sys.executable, os.path.join(HERE, "cmake_gen.py"),
                             os.path.abspath(args.app), variables)
    with open(os.path.join(project, "CMakeLists.txt"), "w", encoding="utf-8") as file:
        file.write(text)
    return directory


def cmd_build(args, variables: dict) -> int:
    for tool in ("cmake", "ninja"):
        if shutil.which(tool) is None:
            print(f"error: {tool} is required", file=sys.stderr)
            return 1
    directory = cmd_generate(args, variables)
    configure = ["cmake", "-G", "Ninja", "-S", os.path.join(directory, "project"),
                 "-B", directory]
    if subprocess.run(configure, check=False).returncode != 0:
        return 1
    build = ["cmake", "--build", directory, "--", f"-j{args.jobs}"]
    return 0 if subprocess.run(build, check=False).returncode == 0 else 1


def main(argv=None) -> int:
    args, variables = parse(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "plan":
            return cmd_plan(args, variables)
        if args.command == "generate":
            print(os.path.join(cmd_generate(args, variables), "project", "CMakeLists.txt"))
            return 0
        return cmd_build(args, variables)
    except OutOfScope as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    except pkg_prepare.PackageError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
