# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Flash data (step G3-2): format, validator, file names and the generator
of the Make adapters.

The programmer and flasher settings of a Make file are a rule list in a YAML
file next to it; the Make file includes the adapter generated from it as its
first statement:

  Make file                       flash data             adapter (generated)
  <dir>/Makefile.include          <dir>/flash.yaml       <dir>/flash.inc.mk
  <dir>/<x>.inc.mk                <dir>/<x>.flash.yaml   <dir>/<x>.flash.inc.mk

Format: `{schema: 3, rules: [...]}`, the rule language of the configuration
data (dist/tools/config_data/README.md, schema 3) plus two constructs of
the flash data:

  construct                            meaning                       Make (generated)
  action `export: {targets, vars}`     the variables reach the       $(call target-export-variables,T,V…)
                                       flasher's environment
                                       (makefiles/utils/variables.mk)
  condition `command: {var}`           the shell finds the command   ifneq (,$(shell command -v $(V)))
                                       named by the value of var

Nothing here reads a Make file or runs make.
"""

from __future__ import annotations

import os
import re
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
DATA_NAME, DATA_SUFFIX = "flash.yaml", ".flash.yaml"
ADAPTER_NAME, ADAPTER_SUFFIX = "flash.inc.mk", ".flash.inc.mk"
FLASH_ACTIONS = ("export",)
FLASH_CONDITIONS = ("command",)
# a target word of `export`: a literal target or pattern, or ${NAME}
TARGET_RE = re.compile(r"^(?:[^\s$(),#]+|\$\{[A-Za-z_][A-Za-z0-9_]*\})$")


# --- names ----------------------------------------------------------------------
def data_name(make_path: str) -> str:
    """The flash data file of a Make file (ValueError if it cannot have one)."""
    directory, base = os.path.split(make_path)
    if base == "Makefile.include":
        return os.path.join(directory, DATA_NAME)
    if base.endswith(".inc.mk") and not base.endswith(ADAPTER_SUFFIX) \
            and base != ADAPTER_NAME and len(base) > len(".inc.mk"):
        return os.path.join(directory, base[:-len(".inc.mk")] + DATA_SUFFIX)
    raise ValueError(f"no flash data name for {make_path}")


def adapter_name(data_path: str) -> str:
    """The generated Make file of a flash data file."""
    directory, base = os.path.split(data_path)
    if base == DATA_NAME:
        return os.path.join(directory, ADAPTER_NAME)
    if base.endswith(DATA_SUFFIX) and len(base) > len(DATA_SUFFIX):
        return os.path.join(directory, base[:-len(DATA_SUFFIX)] + ADAPTER_SUFFIX)
    raise ValueError(f"not a flash data file: {data_path}")


def owner_name(data_path: str) -> str:
    """The hand-written Make file whose flash part the data is."""
    directory, base = os.path.split(data_path)
    if base == DATA_NAME:
        return os.path.join(directory, "Makefile.include")
    return os.path.join(directory, base[:-len(DATA_SUFFIX)] + ".inc.mk")


def is_data_name(path: str) -> bool:
    base = os.path.basename(path)
    return base == DATA_NAME or (base.endswith(DATA_SUFFIX) and len(base) > len(DATA_SUFFIX))


def include_line(data_path: str) -> str:
    """The line of the owner Make file that reads the adapter."""
    adapter = os.path.relpath(adapter_name(data_path), RIOTBASE)
    for prefix, var in (("makefiles/", "RIOTMAKE"), ("boards/", "RIOTBOARD"),
                        ("cpu/", "RIOTCPU")):
        if adapter.startswith(prefix):
            return f"include $({var})/{adapter[len(prefix):]}"
    return f"include $(RIOTBASE)/{adapter}"


def all_data(root: str = RIOTBASE) -> list:
    """Every flash data file of the repository."""
    found = []
    for top in ("boards", "cpu", "makefiles"):
        for directory, _, files in os.walk(os.path.join(root, top)):
            found += [os.path.join(directory, f) for f in files if is_data_name(f)]
    return sorted(found)


# --- validator ------------------------------------------------------------------
def _condition_problems(cond, where, negated=False):
    if isinstance(cond, dict) and len(cond) == 1:
        (key, value), = cond.items()
        if key == "command":
            problems = S._keys_problems(value, f"{where}.command", ("var",))  # pylint: disable=protected-access
            if not problems:
                problems += S._name_problems(value["var"], f"{where}.command.var")  # pylint: disable=protected-access
            return problems
        if key == "not" and not negated:
            return _condition_problems(value, f"{where}.not", negated=True)
    return S.condition_problems(cond, where, negated)


def _export_problems(value, where):
    problems = S._keys_problems(value, where, ("targets", "vars"))  # pylint: disable=protected-access
    if problems:
        return problems
    targets = value["targets"]
    if not isinstance(targets, str) or not targets.split():
        problems.append(f"{where}.targets: a non-empty text of target words")
    else:
        problems += [f"{where}.targets: {w!r} is not a target or ${{NAME}}"
                     for w in targets.split() if not TARGET_RE.match(w)]
    if not isinstance(value["vars"], list) or not value["vars"]:
        problems.append(f"{where}.vars: must be a non-empty list of variable names")
    else:
        for i, name in enumerate(value["vars"]):
            problems += S._name_problems(name, f"{where}.vars[{i}]")  # pylint: disable=protected-access
    return problems


def rules_problems(rules, where="rules") -> list:
    """Problems of a flash rule list: the rule language of the configuration
    data plus `export` and `command`."""
    if not isinstance(rules, list):
        return [f"{where}: must be a list"]
    problems = []
    for i, rule in enumerate(rules):
        here = f"{where}[{i}]"
        if isinstance(rule, dict) and "export" in rule:
            extra = [k for k in rule if k not in ("export", "comment")]
            problems += [f"{here}: unknown key {k!r} next to export" for k in extra]
            problems += _export_problems(rule["export"], f"{here}.export")
        elif isinstance(rule, dict) and "if" in rule:
            problems += _condition_problems(rule["if"], f"{here}.if")
            if "then" not in rule:
                problems.append(f"{here}: if without then")
            unknown = [k for k in rule if k not in ("if", "then", "elif", "else", "comment")]
            problems += [f"{here}: unknown key {k!r}" for k in unknown]
            for branch in ("then", "else"):
                if branch in rule:
                    problems += rules_problems(rule[branch], f"{here}.{branch}")
            for j, branch in enumerate(rule.get("elif") or []):
                bhere = f"{here}.elif[{j}]"
                problems += S._keys_problems(branch, bhere, ("if", "then"), ("comment",))  # pylint: disable=protected-access
                if isinstance(branch, dict) and "if" in branch and "then" in branch:
                    problems += _condition_problems(branch["if"], f"{bhere}.if")
                    problems += rules_problems(branch["then"], f"{bhere}.then")
            if "elif" in rule and (not isinstance(rule["elif"], list) or not rule["elif"]):
                problems.append(f"{here}.elif: must be a non-empty list")
        else:
            problems += [p.replace("rules[0]", here, 1) for p in S.rules_problems([rule])]
    return problems


def validate(document) -> list:
    """Problems of a whole flash data document (empty: valid)."""
    if not isinstance(document, dict):
        return ["document: must be a mapping with schema and rules"]
    problems = [f"document: unknown key {k!r}" for k in document if k not in ("schema", "rules")]
    if document.get("schema") != SCHEMA:
        problems.append(f"schema: must be {SCHEMA}")
    if "rules" not in document:
        problems.append("document: missing key 'rules'")
    else:
        problems += rules_problems(document["rules"])
    return problems


def load(path: str) -> list:
    """The rules of a flash data file; ValueError with its problems."""
    document = R.load_yaml(path)
    problems = validate(document)
    if problems:
        raise ValueError("\n".join(f"{os.path.relpath(path, RIOTBASE)}: {p}" for p in problems))
    return document["rules"]


# --- generator (the Make adapter) -------------------------------------------------
def condition_text(cond: dict) -> str:
    (key, value), = cond.items()
    negated = key == "not"
    if negated:
        (key, value), = value.items()
    if key == "command":
        kind = "ifeq" if negated else "ifneq"
        return f"{kind} (,$(shell command -v $({value['var']})))"
    return G.condition(cond)


def export_text(value: dict) -> str:
    return (f"$(call target-export-variables,{R.to_make_text(value['targets'])},"
            f"{' '.join(value['vars'])})")


def _if(rule: dict, depth: int) -> list:
    pad = "  " * depth
    out = [pad + condition_text(rule["if"])]
    out += lines(rule.get("then") or [], depth + 1)
    for branch in rule.get("elif") or []:
        if "comment" in branch:
            out += G._comment(branch["comment"], pad)  # pylint: disable=protected-access
        out.append(f"{pad}else {condition_text(branch['if'])}")
        out += lines(branch.get("then") or [], depth + 1)
    if "else" in rule:
        out.append(pad + "else")
        out += lines(rule["else"], depth + 1)
    out.append(pad + "endif")
    return out


def lines(rules: list, depth: int = 0) -> list:
    """Make lines of a flash rule list (the layout of config_data's
    generator; `if` and `export` handled here, every other rule there)."""
    pad = "  " * depth
    out = []
    previous = None
    for rule in rules:
        if depth == 0 and previous is not None and \
                G._paragraph(rule, previous):  # pylint: disable=protected-access
            out.append("")
        if "comment" in rule:
            out += G._comment(rule["comment"], pad)  # pylint: disable=protected-access
        if "if" in rule:
            out += _if(rule, depth)
        elif "export" in rule:
            out.append(pad + export_text(rule["export"]))
        elif set(rule) != {"comment"}:
            out += G._action(rule, pad)  # pylint: disable=protected-access
        previous = rule
    return out


def make_text(rules: list, data_base: str) -> str:
    head = [f"# Generated from {data_base} by dist/tools/flash/flash.py.",
            f"# Do not edit: change {data_base} and run `just generate-flash-data`.", ""]
    return "\n".join(head + lines(rules)) + "\n"


def expected_adapter(path: str) -> str:
    return make_text(load(path), os.path.basename(path))
