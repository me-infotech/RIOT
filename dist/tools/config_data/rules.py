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
SCHEMA = 1

# `${NAME}` in a text: the value of the variable NAME. It is the only
# reference the data format knows; Make functions are not allowed.
NAME = r"[A-Za-z_][A-Za-z0-9_]*"
NAME_RE = re.compile(rf"^{NAME}$")
REF_RE = re.compile(rf"\$\{{({NAME})\}}")

# Make file name <-> YAML file name, in the same directory.
KINDS = (("Makefile.dep", "deps.yaml"), ("Makefile.features", "provides.yaml"))


def yaml_name(make_path: str) -> str:
    """`Makefile.dep` -> `deps.yaml`, `Makefile.<x>.dep` -> `<x>.deps.yaml`,
    `Makefile.features` -> `provides.yaml` (likewise with `<x>.`)."""
    directory, base = os.path.split(make_path)
    for make, data in KINDS:
        suffix = make[len("Makefile"):]
        if base == make:
            return os.path.join(directory, data)
        if base.startswith("Makefile.") and base.endswith(suffix):
            middle = base[len("Makefile."):-len(suffix)]
            if middle and "/" not in middle:
                return os.path.join(directory, f"{middle}.{data}")
    raise ValueError(f"not a dependency or feature file: {make_path}")


def make_name(yaml_path: str) -> str:
    """Inverse of yaml_name()."""
    directory, base = os.path.split(yaml_path)
    for make, data in KINDS:
        if base == data:
            return os.path.join(directory, make)
        if base.endswith("." + data):
            middle = base[:-len(data) - 1]
            return os.path.join(directory, f"Makefile.{middle}{make[len('Makefile'):]}")
    raise ValueError(f"not a configuration data file: {yaml_path}")


def is_yaml_name(path: str) -> bool:
    base = os.path.basename(path)
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
            elif isinstance(value, dict):
                new[key] = Flow(value)
            else:
                new[key] = value
        out.append(new)
    return out


def dump_yaml(rules: list, title: str) -> str:
    """The text of a YAML file: a comment header, `schema` and `rules`."""
    head = "".join(f"# {line}\n" if line else "#\n" for line in title.split("\n"))
    body = yaml.dump({"schema": SCHEMA, "rules": _flowed(rules)}, Dumper=_Dumper,
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
            rule = {"set": {"flavor": "recursive", **rule["set"]}}
        elif "include" in rule:
            inc = {"optional": False, **rule["include"]}
            if "for_each" in inc:
                inc.setdefault("sort", False)
            rule = {"include": inc}
        elif "add" in rule:
            (var, items), = rule["add"].items()
            if out and "add" in out[-1] and var in out[-1]["add"]:
                out[-1] = {"add": {var: out[-1]["add"][var] + list(items)}}
                continue
            rule = {"add": {var: list(items)}}
        out.append(rule)
    return out


def _nested_else(rule: dict) -> list:
    """`elif` branches as the nested if in `else` they mean."""
    other = rule.get("else") or []
    for branch in reversed(rule.get("elif") or []):
        other = [{"if": branch["if"], "then": branch.get("then") or [], "else": other}]
    return other


def _normal_cond(cond: dict) -> dict:
    (key, value), = cond.items()
    if key == "not":
        return {"not": _normal_cond(value)}
    if key in ("has", "selection_equals") and not value.get("except"):
        value = {k: v for k, v in value.items() if k != "except"}
    return {key: value}


def count_rules(rules: list) -> int:
    """Number of rules (without standalone comments), nested ones included."""
    total = 0
    for rule in rules:
        if set(rule) == {"comment"}:
            continue
        total += 1 + count_rules(rule.get("then") or []) + count_rules(rule.get("else") or [])
        total += sum(1 + count_rules(b.get("then") or []) for b in rule.get("elif") or [])
    return total
