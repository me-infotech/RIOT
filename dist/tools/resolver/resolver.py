#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Resolve modules, packages, features and the CPU of a RIOT application
from the configuration data alone (migration step G0-2).

Reads only YAML: the application's riot-app.yaml, the dependency and
feature rules (deps.yaml, provides.yaml), the rule files of the build
system pipeline (makefiles/*.inc.yaml) and features.yaml. It never opens a
Make file and never runs make; the algorithm of Make's pipeline files is
pipeline.py.

  resolver.py [-C APPDIR] [VAR=VALUE…] TARGET…

TARGET: info-modules, info-packages, info-features-used,
info-features-missing, info-features-provided, info-cpu (output as
`make TARGET`), info-debug-variable-NAME, info-boards-supported (with
BOARDS=…; the boards to check, Make takes them from the environment),
json (the resolved state for later steps). VAR=VALUE are command line
variables as for make, e.g. BOARD=nrf52840dk.

Exit status: 0; 1 usage; 2 an error of the configuration (Make's
`$(error …)`); 3 the data does not cover the request.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import pipeline  # noqa: E402
from evaluate import Evaluator, OutOfScope, ResolveError, RIOTBASE, rel  # noqa: E402
from variables import Variables  # noqa: E402

STATE_SCHEMA = 1
APP_FILE = "riot-app.yaml"
INFO_TARGETS = ("info-modules", "info-packages", "info-features-used", "info-features-missing",
                "info-features-provided", "info-cpu")


def _evaluator(app_dir: str, variables: dict) -> Evaluator:
    v = Variables()
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = Evaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)
    return ev


def _run_application(ev, build_system):
    """Evaluate riot-app.yaml; its include of Makefile.include runs
    `build_system` (the pipeline)."""
    path = os.path.join(ev.curdir, APP_FILE)
    if not os.path.isfile(path):
        raise OutOfScope(f"{rel(path)} does not exist: the application is not converted "
                         "to data")
    included = []

    def hook():
        included.append(True)
        build_system()
    ev.hooks["Makefile.include"] = hook
    ev.run_file(path)
    if not included:
        raise ResolveError(f"{rel(path)} does not include ${{RIOTBASE}}/Makefile.include")


def resolve(app_dir: str, variables: dict = None, info_goal: bool = True) -> dict:
    """The resolved state of an application. `variables` are command line
    variables (BOARD, …); `info_goal`: as for Make's info-% goals (the
    warnings about insecure modules are not errors then)."""
    ev = _evaluator(app_dir, dict(variables or {}))
    passes = []

    def build_system():
        pipeline.prelude(ev)
        passes.append(pipeline.application(ev, info_goal))
    _run_application(ev, build_system)
    return state(ev, passes[0])


def state(ev, passes: int) -> dict:
    v = ev.v
    words = v.words
    return {
        "schema": STATE_SCHEMA,
        "application": v.get("APPLICATION"),
        "app_dir": rel(ev.curdir),
        "board": v.get("BOARD"),
        "boarddir": rel(v.get("BOARDDIR")),
        "cpu": v.get("CPU"),
        "cpu_model": v.get("CPU_MODEL"),
        "cpu_core": v.get("CPU_CORE"),
        "cpu_fam": v.get("CPU_FAM"),
        "cpu_arch": v.get("CPU_ARCH"),
        "modules": sorted(set(words("USEMODULE"))),
        "packages": sorted(set(words("USEPKG"))),
        "default_modules": words("DEFAULT_MODULE"),
        "disabled_modules": words("DISABLE_MODULE"),
        "features_provided": sorted(set(words("FEATURES_PROVIDED"))),
        "features_required": sorted(set(words("FEATURES_REQUIRED"))),
        "features_used": words("FEATURES_USED"),
        "features_missing": words("FEATURES_MISSING"),
        "features_optional_used": words("FEATURES_OPTIONAL_USED"),
        "features_optional_missing": words("FEATURES_OPTIONAL_MISSING"),
        "features_conflicting": words("FEATURES_CONFLICTING"),
        "features_used_blacklisted": words("FEATURES_USED_BLACKLISTED"),
        "pkg_paths": [rel(p) + "/" for p in words("PKG_PATHS")],
        "passes": passes,
        "messages": [list(m) for m in ev.messages],
        "data_files": sorted(set(ev.read)),
        "make_only_skipped": sorted(set(ev.skipped)),
        "variables": {k: val for k, val in v.snapshot().items() if k != "CURDIR"},
    }


def boards_supported(app_dir: str, boards: list, variables: dict = None) -> list:
    """`make info-boards-supported` for the given boards
    (makefiles/info-global.inc.mk): the boards the application can be
    built for, sorted."""
    variables = dict(variables or {})
    ev = _evaluator(app_dir, variables)
    candidates = []

    def top():
        pipeline.prelude(ev, board=False)
        candidates.extend(pipeline.candidate_boards(ev.v, boards))
    _run_application(ev, top)
    supported = []
    for board in candidates:
        ev = _evaluator(app_dir, {**variables, "BOARD": board})
        result = []

        def one(ev=ev, result=result):
            pipeline.prelude(ev, board=False)
            pipeline.find_boarddir(ev.v)
            result.append(pipeline.board_supported(ev))
        _run_application(ev, one)
        if result[0]:
            supported.append(board)
    return sorted(supported)


def info(result: dict, target: str) -> list:
    """The lines `make TARGET` prints for the resolved state."""
    if target == "info-modules":
        return result["modules"]
    if target == "info-packages":
        return result["packages"]
    if target == "info-features-used":
        return result["features_used"]
    if target == "info-features-missing":
        return result["features_missing"]
    if target == "info-features-provided":
        return result["features_provided"]
    if target == "info-cpu":
        return [" ".join(result["cpu"].split())]
    if target.startswith("info-debug-variable-"):
        name = target[len("info-debug-variable-"):]
        return [" ".join(result["variables"].get(name, "").split())]
    raise ValueError(f"unknown target {target}")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    app_dir, variables, targets = ".", {}, []
    while args:
        arg = args.pop(0)
        if arg == "-C" and args:
            app_dir = args.pop(0)
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        elif "=" in arg and not arg.startswith("-"):
            name, value = arg.split("=", 1)
            variables[name] = value
        elif arg.startswith("-"):
            print(f"error: unknown option {arg}", file=sys.stderr)
            return 1
        else:
            targets.append(arg)
    if not targets:
        print("error: no target (see --help)", file=sys.stderr)
        return 1
    if not os.path.isabs(app_dir):
        app_dir = os.path.join(os.getcwd(), app_dir)
    out = []
    try:
        result = None
        for target in targets:
            if target == "info-boards-supported":
                boards = variables.pop("BOARDS", "").split()
                if not boards:
                    print("error: info-boards-supported needs BOARDS=…", file=sys.stderr)
                    return 1
                out.append(" ".join(boards_supported(app_dir, boards, variables)))
                continue
            if target not in INFO_TARGETS + ("json",) \
                    and not target.startswith("info-debug-variable-"):
                print(f"error: unknown target {target}", file=sys.stderr)
                return 1
            if result is None:
                result = resolve(app_dir, variables)
                for level, text in result["messages"]:
                    print(f"{level}: {text}", file=sys.stderr)
            if target == "json":
                out.append(json.dumps(result, indent=1, sort_keys=True))
            else:
                out += info(result, target)
    except OutOfScope as err:
        print(f"error: outside the data: {err}", file=sys.stderr)
        return 3
    except ResolveError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["resolve", "boards_supported", "info", "RIOTBASE"]
