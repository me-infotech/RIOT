#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Dependency and feature configuration of RIOT as data (migration step G0-1).

The YAML file next to a `Makefile.dep` (`deps.yaml`) or `Makefile.features`
(`provides.yaml`) is the source; the Make file is generated from it and
checked in, so that Make keeps working until nothing reads it any more.

  config_data.py generate [--check] [YAML…]   write (check) the Make files
  config_data.py validate [YAML…]             check the YAML against the schema
  config_data.py translate [--force] MAKEFILE…
                                              one-off conversion: write the YAML
                                              next to each Make file
  config_data.py roundtrip [--rev REV] [MAKEFILE…]
                                              rules of the original Make file
                                              (at REV) == rules of the generated
                                              file == rules of the YAML
  config_data.py scope [--check | --write]    the files Make reads for the
                                              sample of scope.yaml

Without file arguments, generate/validate use every YAML data file of the
repository and roundtrip uses the files listed in scope.yaml.
"""

import argparse
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import generate  # noqa: E402
import rules as R  # noqa: E402
import schema  # noqa: E402
from translate import Unsupported, translate  # noqa: E402

SCOPE_FILE = os.path.join(HERE, "scope.yaml")
HINT = "Forgot to run `just generate-config-data`? Change the YAML, never the Make file."


def rel(path: str) -> str:
    """Path relative to the repository root (absolute if outside)."""
    path = os.path.abspath(path)
    relative = os.path.relpath(path, R.RIOTBASE)
    return path if relative.startswith("..") else relative


def all_yaml(root: str = R.RIOTBASE) -> list:
    """Every configuration data file of the repository (tracked or new)."""
    try:
        listed = subprocess.run(["git", "-C", root, "ls-files", "--cached", "--others",
                                 "--exclude-standard"], capture_output=True, text=True,
                                check=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError):
        listed = [os.path.relpath(os.path.join(d, f), root)
                  for d, _, files in os.walk(root) for f in files]
    return sorted(os.path.join(root, p) for p in listed
                  if p and R.is_yaml_name(p) and os.path.isfile(os.path.join(root, p)))


def load_valid(path: str) -> list:
    """The rules of a YAML file; ValueError with every schema problem."""
    try:
        document = R.load_yaml(path)
    except yaml.YAMLError as err:
        raise ValueError(f"{rel(path)}: not YAML: {err}") from None
    problems = schema.validate(document)
    if problems:
        raise ValueError("\n".join(f"{rel(path)}: {p}" for p in problems))
    return document["rules"]


def expected_make_text(path: str) -> str:
    return generate.make_text(load_valid(path), os.path.basename(path))


def title(make_path: str) -> str:
    directory = os.path.dirname(rel(make_path)) or "the repository root"
    base = os.path.basename(make_path)
    what = "Dependency rules" if base.endswith(".dep") else "Provided features and CPU data"
    return (f"{what} of {directory}. This file is the source: {base}\n"
            "next to it is generated from it (`just generate-config-data`).\n"
            "Format: dist/tools/config_data/README.md")


def roundtrip_problems(original_text: str, generated_text: str, yaml_rules: list) -> list:
    """Compare the normalised rules of the three representations."""
    problems = []
    original = R.normalise(translate(original_text, "original"))
    if R.normalise(translate(generated_text, "generated")) != original:
        problems.append("rules of the generated Make file differ from the original")
    if R.normalise(yaml_rules) != original:
        problems.append("rules of the YAML differ from the original")
    return problems


def cmd_translate(args) -> int:
    failed = 0
    for make_path in args.files:
        target = R.yaml_name(make_path)
        try:
            with open(make_path, encoding="utf-8") as file:
                original = file.read()
            rules = translate(original, rel(make_path))
            text = R.dump_yaml(rules, title(make_path))
            document = yaml.safe_load(text)
            problems = schema.validate(document)
            problems += roundtrip_problems(
                original, generate.make_text(document["rules"], os.path.basename(target)),
                document["rules"])
        except Unsupported as err:
            print(f"error: {err}", file=sys.stderr)
            failed += 1
            continue
        if problems:
            print("\n".join(f"error: {rel(make_path)}: {p}" for p in problems), file=sys.stderr)
            failed += 1
            continue
        if os.path.exists(target) and not args.force:
            print(f"error: {rel(target)} exists (use --force)", file=sys.stderr)
            failed += 1
            continue
        with open(target, "w", encoding="utf-8") as file:
            file.write(text)
        print(f"{rel(target)}: {R.count_rules(rules)} rules")
    return 1 if failed else 0


def cmd_generate(args) -> int:
    files = args.files or all_yaml()
    stale = 0
    for path in files:
        make_path = R.make_name(path)
        try:
            text = expected_make_text(path)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            stale += 1
            continue
        current = None
        if os.path.exists(make_path):
            with open(make_path, encoding="utf-8") as file:
                current = file.read()
        if current == text:
            continue
        if args.check:
            print(f"{rel(make_path)} is not up to date with {os.path.basename(path)}",
                  file=sys.stderr)
            stale += 1
        else:
            with open(make_path, "w", encoding="utf-8") as file:
                file.write(text)
            print(f"wrote {rel(make_path)}")
    if stale and args.check:
        print(HINT, file=sys.stderr)
    return 1 if stale else 0


def cmd_validate(args) -> int:
    failed = 0
    for path in args.files or all_yaml():
        try:
            load_valid(path)
        except ValueError as err:
            print(err, file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def load_scope() -> dict:
    with open(SCOPE_FILE, encoding="utf-8") as file:
        return yaml.safe_load(file)


def git_show(rev: str, path: str) -> str:
    return subprocess.run(["git", "-C", R.RIOTBASE, "show", f"{rev}:{path}"],
                          capture_output=True, text=True, check=True).stdout


def cmd_roundtrip(args) -> int:
    scope = load_scope()
    rev = args.rev or scope["base"]
    files = [rel(f) for f in args.files] or scope["files"]
    failed = 0
    for path in files:
        yaml_path = os.path.join(R.RIOTBASE, R.yaml_name(path))
        with open(os.path.join(R.RIOTBASE, path), encoding="utf-8") as file:
            generated = file.read()
        try:
            problems = roundtrip_problems(git_show(rev, path), generated, load_valid(yaml_path))
        except (ValueError, subprocess.CalledProcessError) as err:
            problems = [str(err).strip()]
        for problem in problems:
            print(f"{path}: {problem}", file=sys.stderr)
        failed += bool(problems)
    print(f"{len(files) - failed}/{len(files)} files: original = generated = YAML (rev {rev[:10]})")
    return 1 if failed else 0


def make_read_files(apps: dict, boards: list) -> list:
    """Dependency and feature files in MAKEFILE_LIST, over all pairs."""
    found = set()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C"}
    for app_dir in apps.values():
        for board in boards:
            out = subprocess.run(["make", "--no-print-directory", "-C", app_dir,
                                  f"BOARD={board}", "info-debug-variable-MAKEFILE_LIST"],
                                 cwd=R.RIOTBASE, env=env, capture_output=True, text=True,
                                 check=True).stdout
            for word in out.split():
                path = os.path.relpath(os.path.normpath(os.path.join(R.RIOTBASE, app_dir, word)),
                                       R.RIOTBASE)
                base = os.path.basename(path)
                if base.startswith("Makefile") and base.endswith((".dep", ".features")):
                    found.add(path)
    return sorted(found)


def cmd_scope(args) -> int:
    scope = load_scope()
    files = make_read_files(scope["applications"], scope["boards"])
    if args.write:
        scope["files"] = files
        with open(SCOPE_FILE, "r", encoding="utf-8") as file:
            head = "".join(line for line in file if line.startswith("#"))
        with open(SCOPE_FILE, "w", encoding="utf-8") as file:
            file.write(head + yaml.safe_dump(scope, sort_keys=False, width=100))
    if args.check and files != scope["files"]:
        print("scope.yaml differs from the files Make reads:\n  missing: "
              f"{sorted(set(files) - set(scope['files']))}\n  extra: "
              f"{sorted(set(scope['files']) - set(files))}", file=sys.stderr)
        return 1
    if not args.check:
        print("\n".join(files))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("generate")
    cmd.add_argument("--check", action="store_true")
    cmd.add_argument("files", nargs="*")
    cmd.set_defaults(func=cmd_generate)
    cmd = sub.add_parser("validate")
    cmd.add_argument("files", nargs="*")
    cmd.set_defaults(func=cmd_validate)
    cmd = sub.add_parser("translate")
    cmd.add_argument("--force", action="store_true")
    cmd.add_argument("files", nargs="+")
    cmd.set_defaults(func=cmd_translate)
    cmd = sub.add_parser("roundtrip")
    cmd.add_argument("--rev")
    cmd.add_argument("files", nargs="*")
    cmd.set_defaults(func=cmd_roundtrip)
    cmd = sub.add_parser("scope")
    group = cmd.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    cmd.set_defaults(func=cmd_scope)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
