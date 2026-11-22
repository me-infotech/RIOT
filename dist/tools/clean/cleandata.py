# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Clean data (step G2C-1): format, validator, file names and the generator
of the Make adapters.

The settings of `clean` in a Make file are a rule list in a YAML file next
to it; the Make file includes the adapter generated from it as its first
statement:

  Make file              clean data              adapter (generated)
  <dir>/<x>.inc.mk       <dir>/<x>.clean.yaml    <dir>/<x>.clean.inc.mk

Format: `{schema: 3, rules: [...]}`, the rule language of the configuration
data (dist/tools/config_data/README.md, schema 3) without the build-only
constructs (`section`, `stand_in`): every rule is written as Make.

Nothing here reads a Make file or runs make.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _sub in ("config_data", "resolver", "cmake_gen"):
    if os.path.join(TOOLS, _sub) not in sys.path:
        sys.path.insert(0, os.path.join(TOOLS, _sub))

# pylint: disable=wrong-import-position
import generate as G  # noqa: E402
import rules as R  # noqa: E402
import schema as S  # noqa: E402

RIOTBASE = R.RIOTBASE
SCHEMA = 3
DATA_SUFFIX = ".clean.yaml"
ADAPTER_SUFFIX = ".clean.inc.mk"
NOT_IN_CLEAN_DATA = ("section", "stand_in")


# --- names ----------------------------------------------------------------------
def data_name(make_path: str) -> str:
    """The clean data file of a Make file (ValueError if it cannot have
    one)."""
    directory, base = os.path.split(make_path)
    if base.endswith(".inc.mk") and not base.endswith(ADAPTER_SUFFIX) \
            and len(base) > len(".inc.mk"):
        return os.path.join(directory, base[:-len(".inc.mk")] + DATA_SUFFIX)
    raise ValueError(f"no clean data name for {make_path}")


def adapter_name(data_path: str) -> str:
    """The generated Make file of a clean data file."""
    directory, base = os.path.split(data_path)
    if base.endswith(DATA_SUFFIX) and len(base) > len(DATA_SUFFIX):
        return os.path.join(directory, base[:-len(DATA_SUFFIX)] + ADAPTER_SUFFIX)
    raise ValueError(f"not a clean data file: {data_path}")


def owner_name(data_path: str) -> str:
    """The hand-written Make file whose clean part the data is."""
    directory, base = os.path.split(data_path)
    return os.path.join(directory, base[:-len(DATA_SUFFIX)] + ".inc.mk")


def is_data_name(path: str) -> bool:
    base = os.path.basename(path)
    return base.endswith(DATA_SUFFIX) and len(base) > len(DATA_SUFFIX)


def include_line(data_path: str) -> str:
    """The line of the owner Make file that reads the adapter."""
    adapter = os.path.relpath(adapter_name(data_path), RIOTBASE)
    if adapter.startswith("makefiles/"):
        return f"include $(RIOTMAKE)/{adapter[len('makefiles/'):]}"
    return f"include $(RIOTBASE)/{adapter}"


def all_data(root: str = RIOTBASE) -> list:
    """Every clean data file of the repository (makefiles/)."""
    found = []
    for directory, _, files in os.walk(os.path.join(root, "makefiles")):
        found += [os.path.join(directory, f) for f in files if is_data_name(f)]
    return sorted(found)


# --- validator ------------------------------------------------------------------
def _build_only(rules, where="rules") -> list:
    problems = []
    for i, rule in enumerate(rules if isinstance(rules, list) else []):
        if not isinstance(rule, dict):
            continue
        problems += [f"{where}[{i}]: {key!r} is build data only" for key in NOT_IN_CLEAN_DATA
                     if key in rule]
        for branch in ("then", "else"):
            problems += _build_only(rule.get(branch), f"{where}[{i}].{branch}")
        for j, branch in enumerate(rule.get("elif") or []):
            if isinstance(branch, dict):
                problems += _build_only(branch.get("then"), f"{where}[{i}].elif[{j}].then")
    return problems


def validate(document) -> list:
    """Problems of a whole clean data document (empty: valid)."""
    if not isinstance(document, dict):
        return ["document: must be a mapping with schema and rules"]
    problems = [f"document: unknown key {k!r}" for k in document if k not in ("schema", "rules")]
    if document.get("schema") != SCHEMA:
        problems.append(f"schema: must be {SCHEMA}")
    if "rules" not in document:
        return problems + ["document: missing key 'rules'"]
    problems += S.rules_problems(document["rules"]) + _build_only(document["rules"])
    return problems


def load(path: str) -> list:
    """The rules of a clean data file; ValueError with its problems."""
    document = R.load_yaml(path)
    problems = validate(document)
    if problems:
        raise ValueError("\n".join(f"{os.path.relpath(path, RIOTBASE)}: {p}" for p in problems))
    return document["rules"]


# --- generator (the Make adapter) -------------------------------------------------
def make_text(rules: list, data_base: str) -> str:
    head = [f"# Generated from {data_base} by dist/tools/clean/clean.py.",
            f"# Do not edit: change {data_base} and run `just generate-clean-data`.", ""]
    return "\n".join(head + G.lines(rules)) + "\n"


def expected_adapter(path: str) -> str:
    return make_text(load(path), os.path.basename(path))
