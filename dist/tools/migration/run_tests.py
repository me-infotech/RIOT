#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Run the unit tests of the migration steps listed in steps.yaml.

Examples (from the repository root):

    dist/tools/migration/run_tests.py --list
    dist/tools/migration/run_tests.py                       # all steps
    dist/tools/migration/run_tests.py --step p3-task-layer-group1
    dist/tools/migration/run_tests.py --group 1
    dist/tools/migration/run_tests.py --target print-versions
    dist/tools/migration/run_tests.py --matrix              # CI job matrix

Every test directory runs in its own `python -m unittest discover`, so test
modules of different steps never share a process or a module name.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
STEPS_FILE = os.path.join(HERE, "steps.yaml")

GROUPS = ("1", "2A", "2B", "2C", "3")
STEP_KEYS = {"id", "title", "group", "targets", "tests", "requires", "docs"}
TARGET_KEYS = {"name", "now", "hardware", "board_test"}
ID_PATTERN = re.compile(r"^p[0-9]+-[a-z0-9]+(-[a-z0-9]+)*$")


def load(path=STEPS_FILE):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)["steps"]


def validate(steps, root=RIOTBASE):
    """Return a list of problems; empty if the register is consistent."""
    problems = []
    seen_ids, seen_targets = set(), {}
    for step in steps:
        sid = step.get("id", "<no id>")
        where = f"step {sid}"
        problems += [f"{where}: unknown key {k!r}" for k in sorted(set(step) - STEP_KEYS)]
        problems += [f"{where}: missing key {k!r}" for k in sorted(STEP_KEYS - set(step))]
        if not ID_PATTERN.match(str(sid)):
            problems.append(f"{where}: id must look like p3-topic-words")
        if sid in seen_ids:
            problems.append(f"{where}: duplicate id")
        seen_ids.add(sid)
        if str(step.get("group")) not in GROUPS:
            problems.append(f"{where}: group must be one of {', '.join(GROUPS)}")
        if not step.get("targets"):
            problems.append(f"{where}: no targets")
        for target in step.get("targets") or []:
            name = target.get("name", "<no name>")
            problems += [f"{where}: target {name}: unknown key {k!r}"
                         for k in sorted(set(target) - TARGET_KEYS)]
            if "now" not in target or "hardware" not in target:
                problems.append(f"{where}: target {name}: needs 'now' and 'hardware'")
            if target.get("hardware") and not target.get("board_test"):
                problems.append(f"{where}: target {name}: hardware target needs 'board_test'")
            if name in seen_targets:
                problems.append(f"{where}: target {name} already in step {seen_targets[name]}")
            seen_targets[name] = sid
        if not step.get("tests"):
            problems.append(f"{where}: no tests")
        for test_dir in step.get("tests") or []:
            path = os.path.join(root, test_dir)
            if not os.path.isdir(path):
                problems.append(f"{where}: test directory {test_dir} does not exist")
            elif not any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(path)):
                problems.append(f"{where}: {test_dir} has no test_*.py")
        docs = step.get("docs")
        if docs and not os.path.isfile(os.path.join(root, docs)):
            problems.append(f"{where}: docs file {docs} does not exist")
    return problems


def select(steps, step=None, group=None, target=None):
    chosen = steps
    if step:
        chosen = [s for s in chosen if s["id"] == step]
    if group:
        chosen = [s for s in chosen if str(s["group"]) == group]
    if target:
        chosen = [s for s in chosen if any(t["name"] == target for t in s["targets"])]
    return chosen


def matrix(steps):
    return {"include": [{
        "id": s["id"],
        "group": str(s["group"]),
        "pip": " ".join(s["requires"].get("pip", [])),
        "tools": ",".join(s["requires"].get("tools", [])),
    } for s in steps]}


def run_step(step, verbosity):
    ok = True
    for test_dir in step["tests"]:
        print(f"== {step['id']} (group {step['group']}): {test_dir}", flush=True)
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", test_dir, "-t", test_dir]
        if verbosity:
            cmd.append("-v")
        ok &= subprocess.run(cmd, cwd=RIOTBASE, check=False).returncode == 0
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--step")
    parser.add_argument("--group", choices=GROUPS)
    parser.add_argument("--target")
    parser.add_argument("--list", action="store_true", help="list steps and targets")
    parser.add_argument("--matrix", action="store_true", help="print the CI job matrix")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    steps = load()
    problems = validate(steps)
    if problems:
        print("steps.yaml is inconsistent:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2

    chosen = select(steps, args.step, args.group, args.target)
    if not chosen:
        print("no step matches", file=sys.stderr)
        return 2
    if args.matrix:
        print(json.dumps(matrix(chosen)))
        return 0
    if args.list:
        for s in chosen:
            names = ", ".join(t["name"] for t in s["targets"])
            print(f"{s['id']:<28} group {s['group']:<3} {names}")
        return 0

    results = [(s["id"], run_step(s, args.verbose)) for s in chosen]
    print("\nSummary:")
    for sid, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {sid}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
