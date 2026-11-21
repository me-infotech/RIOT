# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Shared parts of the configuration data tools: file names, variable
references in text, YAML input/output and the normal form of a rule list.

A rule list is the content of `rules:` in a YAML file (see README.md); the
translator produces it from a Make file, the generator writes a Make file
from it, and the validator checks it.
"""

import os
import re

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
# Schema 1: the format of step G0-1. Schema 2 (step G0-2) adds selections
# (`select` values, `${NAME}` as a pattern word, the `several` condition) for
# the rules of the build system pipeline; every schema-1 document is also a
# valid schema-2 document. A file declares the lowest schema it needs.
SCHEMA = 2
SCHEMAS = (1, 2)

# `${NAME}` in a text: the value of the variable NAME. It is the only
# reference the data format knows; Make functions are not allowed.
NAME = r"[A-Za-z_][A-Za-z0-9_]*"
NAME_RE = re.compile(rf"^{NAME}$")
REF_RE = re.compile(rf"\$\{{({NAME})\}}")

# Make file name <-> YAML file name, in the same directory.
KINDS = (("Makefile.dep", "deps.yaml"), ("Makefile.features", "provides.yaml"),
         ("Makefile.default", "default.yaml"))
# The application Makefile (step G0-2) and the rule files of the build
# system pipeline in makefiles/ (`<name>.inc.mk`).
APP_MAKE, APP_DATA = "Makefile", "riot-app.yaml"
INC_MAKE, INC_DATA = ".inc.mk", ".inc.yaml"


def yaml_name(make_path: str) -> str:
    """`Makefile.dep` -> `deps.yaml`, `Makefile.<x>.dep` -> `<x>.deps.yaml`,
    `Makefile.features` -> `provides.yaml`, `Makefile.default` ->
    `default.yaml` (likewise with `<x>.`), `<name>.inc.mk` ->
    `<name>.inc.yaml`, an application's `Makefile` -> `riot-app.yaml`."""
    directory, base = os.path.split(make_path)
    if base == APP_MAKE:
        return os.path.join(directory, APP_DATA)
    if base.endswith(INC_MAKE) and len(base) > len(INC_MAKE):
        return os.path.join(directory, base[:-len(INC_MAKE)] + INC_DATA)
    for make, data in KINDS:
        suffix = make[len("Makefile"):]
        if base == make:
            return os.path.join(directory, data)
        if base.startswith("Makefile.") and base.endswith(suffix):
            middle = base[len("Makefile."):-len(suffix)]
            if middle and "/" not in middle:
                return os.path.join(directory, f"{middle}.{data}")
    raise ValueError(f"not a file of the configuration data: {make_path}")


def make_name(yaml_path: str) -> str:
    """Inverse of yaml_name()."""
    directory, base = os.path.split(yaml_path)
    if base == APP_DATA:
        return os.path.join(directory, APP_MAKE)
    if base.endswith(INC_DATA) and len(base) > len(INC_DATA):
        return os.path.join(directory, base[:-len(INC_DATA)] + INC_MAKE)
    for make, data in KINDS:
        if base == data:
            return os.path.join(directory, make)
        if base.endswith("." + data):
            middle = base[:-len(data) - 1]
            return os.path.join(directory, f"Makefile.{middle}{make[len('Makefile'):]}")
    raise ValueError(f"not a configuration data file: {yaml_path}")


def is_yaml_name(path: str) -> bool:
    base = os.path.basename(path)
    if base == APP_DATA or (base.endswith(INC_DATA) and len(base) > len(INC_DATA)):
        return True
    return any(base == data or base.endswith("." + data) for _, data in KINDS)


def to_make_text(text: str) -> str:
    """`${NAME}` -> `$(NAME)`."""
    return REF_RE.sub(r"$(\1)", text)


# --- YAML -------------------------------------------------------------------
class Flow(dict):
    """A mapping written on one line (conditions and actions)."""


class _Dumper(yaml.SafeDumper):
    # pylint: disable=too-many-ancestors
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _represent_flow(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True)


def _represent_str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_str(data)


_Dumper.add_representer(Flow, _represent_flow)
_Dumper.add_representer(str, _represent_str)


def _flowed(rules: list) -> list:
    out = []
    for rule in rules:
        new = {}
        for key, value in rule.items():
            if key in ("then", "else", "elif"):
                new[key] = _flowed(value)
            elif key == "set" and isinstance(value.get("value"), dict):
                new[key] = {**value, "value": Flow(value["value"])}
            elif isinstance(value, dict):
                new[key] = Flow(value)
            else:
                new[key] = value
        out.append(new)
    return out


# --- schema 2 ---------------------------------------------------------------
def walk(rules: list):
    """Every rule, nested ones included (depth first, in order)."""
    for rule in rules:
        yield rule
        yield from walk(rule.get("then") or [])
        for branch in rule.get("elif") or []:
            yield from walk(branch.get("then") or [])
        yield from walk(rule.get("else") or [])


def conditions(rules: list):
    """Every condition (inside `not` too) of a rule list."""
    for rule in walk(rules):
        for cond in [rule.get("if")] + [b["if"] for b in rule.get("elif") or []]:
            while isinstance(cond, dict) and "not" in cond:
                cond = cond["not"]
            if isinstance(cond, dict):
                yield cond


def is_ref_word(word) -> bool:
    """`${NAME}` as a whole word: the words of NAME (schema 2)."""
    return isinstance(word, str) and REF_RE.fullmatch(word) is not None


def _schema2_selection(sel) -> bool:
    return isinstance(sel, dict) and any(
        is_ref_word(w) for key in ("match", "except") for w in sel.get(key) or [])


def needed_schema(rules: list) -> int:
    """1 unless the rules use a construct of schema 2."""
    for cond in conditions(rules):
        (key, value), = cond.items()
        if key == "several" or _schema2_selection(value):
            return 2
    for rule in walk(rules):
        if "add" in rule and any(isinstance(i, dict)
                                 for items in rule["add"].values() for i in items):
            return 2
        if "set" in rule and isinstance(rule["set"].get("value"), dict):
            return 2
    return 1


def uses_several(rules: list) -> bool:
    return any("several" in cond for cond in conditions(rules))


def dump_yaml(rules: list, title: str) -> str:
    """The text of a YAML file: a comment header, `schema` (the lowest one
    the rules need) and `rules`."""
    head = "".join(f"# {line}\n" if line else "#\n" for line in title.split("\n"))
    body = yaml.dump({"schema": needed_schema(rules), "rules": _flowed(rules)}, Dumper=_Dumper,
                     sort_keys=False, width=100, allow_unicode=True)
    return head + body


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


# --- normal form ----------------------------------------------------------------
def normalise(rules: list) -> list:
    """The meaning of a rule list, for comparison: comments dropped, default
    values made explicit, adjacent `add` of the same variable merged (Make
    reads `V += a` `V += b` like `V += a b`)."""
    out = []
    for rule in rules:
        rule = {k: v for k, v in rule.items() if k != "comment"}
        if not rule:
            continue
        if "if" in rule:
            rule = {"if": _normal_cond(rule["if"]),
                    "then": normalise(rule.get("then") or []),
                    "else": normalise(_nested_else(rule))}
        elif "set" in rule:
            rule = {"set": {"flavor": "recursive", **rule["set"],
                            "value": _normal_value(rule["set"]["value"])}}
        elif "include" in rule:
            inc = {"optional": False, **rule["include"]}
            if "for_each" in inc:
                inc.setdefault("sort", False)
            rule = {"include": inc}
        elif "add" in rule:
            (var, items), = rule["add"].items()
            items = [_normal_value(i) for i in items]
            if out and "add" in out[-1] and var in out[-1]["add"]:
                out[-1] = {"add": {var: out[-1]["add"][var] + items}}
                continue
            rule = {"add": {var: items}}
        out.append(rule)
    return out


def _nested_else(rule: dict) -> list:
    """`elif` branches as the nested if in `else` they mean."""
    other = rule.get("else") or []
    for branch in reversed(rule.get("elif") or []):
        other = [{"if": branch["if"], "then": branch.get("then") or [], "else": other}]
    return other


def _normal_selection(sel: dict) -> dict:
    return {k: v for k, v in sel.items() if v or k not in ("except", "match")}


def _normal_cond(cond: dict) -> dict:
    (key, value), = cond.items()
    if key == "not":
        return {"not": _normal_cond(value)}
    if key in ("has", "selection_equals", "several"):
        value = _normal_selection(value)
    return {key: value}


def _normal_value(value):
    if isinstance(value, dict):
        return {"select": _normal_selection(value["select"])}
    return value


def count_rules(rules: list) -> int:
    """Number of rules (without standalone comments), nested ones included."""
    total = 0
    for rule in rules:
        if set(rule) == {"comment"}:
            continue
        total += 1 + count_rules(rule.get("then") or []) + count_rules(rule.get("else") or [])
        total += sum(1 + count_rules(b.get("then") or []) for b in rule.get("elif") or [])
    return total
