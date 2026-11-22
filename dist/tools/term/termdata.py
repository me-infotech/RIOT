# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Terminal and debugger data (step G2B-1): format, validator, file names and
the generator of the Make adapters.

The terminal settings (`term`) and the debugger settings the terminal needs
(`debug`: DEBUGGER for RIOT_TERMINAL=semihosting, reused by the later step of
`debug`) of a Make file are rule lists in YAML files next to it; the Make
file includes the adapters generated from them, after its flash adapter
(dist/tools/flash, step G3-2):

  Make file                  data                          adapter (generated)
  <dir>/Makefile.include     <dir>/debug.yaml              <dir>/debug.inc.mk
                             <dir>/term.yaml               <dir>/term.inc.mk
  <dir>/<x>.inc.mk           <dir>/<x>.debug.yaml          <dir>/<x>.debug.inc.mk
                             <dir>/<x>.term.yaml           <dir>/<x>.term.inc.mk

Format: `{schema: 4, rules: [...]}`, the rule language of the flash data
(dist/tools/flash/flashdata.py: the configuration data of
dist/tools/config_data/README.md plus `export: {targets, vars}` and the
condition `command: {var}`) without `section`, plus three constructs of this step:

  construct                         meaning                         Make (generated)
  condition `command: {name}`       the shell finds the command     ifneq (,$(shell command -v NAME 2>/dev/null))
                                    NAME
  value `{word: {var, index}}`      word `index` of var (1 first,   $(firstword $(V)), $(lastword $(V)),
                                    -1 last)                        $(word N,$(V))
  `set: {…, export: true}`          the variable is exported to     export V ?= …
                                    every command (schema 4)

A rule with `stand_in: <owner Make file>` (schema 4, step G0-3) is read by
the terminal without Make and left out of the adapter: the owner Make file
still does it itself (jlink.inc.mk and openocd.inc.mk include
dbg_common.inc.mk before their flash adapter, as before this step).

The answers of the shell the data needs (the TTY found by ttys.py, the
time stamp of the pyterm session, the macOS USB modems) are the probe
variables PROBE_TTY_DETECTED, PROBE_DATE_TIME and PROBE_TTY_USBMODEM, as the
build data reads the toolchain probes (step G0-3): for Make they are defined
in makefiles/term_providers.inc.mk, dist/tools/term/term.py computes them.

Nothing here reads a Make file or runs make.
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _sub in ("flash", "config_data", "resolver", "cmake_gen"):
    if os.path.join(TOOLS, _sub) not in sys.path:
        sys.path.insert(0, os.path.join(TOOLS, _sub))

# pylint: disable=wrong-import-position,protected-access
import flashdata as F  # noqa: E402
import generate as G  # noqa: E402
import rules as R  # noqa: E402
import schema as S  # noqa: E402

RIOTBASE = R.RIOTBASE
SCHEMA = 4
# the data kinds of this step, in the order an owner includes its adapters
# (after the flash adapter)
KINDS = ("debug", "term")
NOT_IN_DATA = ("section",)
COMMAND_NAME_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
# the top directories with data; the repository root holds debug.yaml of
# Makefile.include
TOPS = ("boards", "cpu", "makefiles")


# --- names ----------------------------------------------------------------------
def data_name(make_path: str, kind: str) -> str:
    """The `kind` data file of a Make file (ValueError if it cannot have one)."""
    directory, base = os.path.split(make_path)
    if base == "Makefile.include":
        return os.path.join(directory, f"{kind}.yaml")
    if base.endswith(".inc.mk") and len(base) > len(".inc.mk") and \
            not any(base == f"{k}.inc.mk" or base.endswith(f".{k}.inc.mk")
                    for k in KINDS + ("flash",)):
        return os.path.join(directory, base[:-len(".inc.mk")] + f".{kind}.yaml")
    raise ValueError(f"no {kind} data name for {make_path}")


def kind_of(path: str):
    """The kind of a data file name, None if it is none."""
    base = os.path.basename(path)
    for kind in KINDS:
        if base == f"{kind}.yaml" or (base.endswith(f".{kind}.yaml")
                                      and len(base) > len(f".{kind}.yaml")):
            return kind
    return None


def is_data_name(path: str) -> bool:
    return kind_of(path) is not None


def adapter_name(data_path: str) -> str:
    """The generated Make file of a data file."""
    kind = kind_of(data_path)
    if kind is None:
        raise ValueError(f"not a terminal or debugger data file: {data_path}")
    return data_path[:-len(".yaml")] + ".inc.mk"


def owner_name(data_path: str) -> str:
    """The hand-written Make file whose part the data is."""
    kind = kind_of(data_path)
    directory, base = os.path.split(data_path)
    if base == f"{kind}.yaml":
        return os.path.join(directory, "Makefile.include")
    return os.path.join(directory, base[:-len(f".{kind}.yaml")] + ".inc.mk")


def include_line(data_path: str) -> str:
    """The line of the owner Make file that reads the adapter (as for the
    flash data)."""
    adapter = os.path.relpath(adapter_name(data_path), RIOTBASE)
    for prefix, var in (("makefiles/", "RIOTMAKE"), ("boards/", "RIOTBOARD"),
                        ("cpu/", "RIOTCPU")):
        if adapter.startswith(prefix):
            return f"include $({var})/{adapter[len(prefix):]}"
    return f"include $(RIOTBASE)/{adapter}"


def all_data(root: str = RIOTBASE) -> list:
    """Every terminal and debugger data file of the repository."""
    found = [os.path.join(root, f) for f in os.listdir(root)
             if is_data_name(f) and os.path.isfile(os.path.join(root, f))]
    for top in TOPS:
        for directory, _, files in os.walk(os.path.join(root, top)):
            found += [os.path.join(directory, f) for f in files if is_data_name(f)]
    return sorted(found)


# --- validator ------------------------------------------------------------------
def condition_problems(cond, where, negated=False) -> list:
    """A condition of the flash data, or `command: {name}`."""
    if isinstance(cond, dict) and len(cond) == 1:
        (key, value), = cond.items()
        if key == "command" and isinstance(value, dict) and "name" in value:
            problems = S._keys_problems(value, f"{where}.command", ("name",))
            if not problems and (not isinstance(value["name"], str)
                                 or not COMMAND_NAME_RE.match(value["name"])):
                problems.append(f"{where}.command.name: {value['name']!r} is not a command name")
            return problems
        if key == "not" and not negated:
            return condition_problems(value, f"{where}.not", negated=True)
    return F._condition_problems(cond, where, negated)


def word_problems(value, where) -> list:
    """`{word: {var, index}}`."""
    problems = S._keys_problems(value, where, ("word",))
    if problems:
        return problems
    body, here = value["word"], f"{where}.word"
    problems = S._keys_problems(body, here, ("var", "index"))
    if problems:
        return problems
    problems += S._name_problems(body["var"], f"{here}.var")
    index = body["index"]
    if not isinstance(index, int) or isinstance(index, bool) or index == 0 or index < -1:
        problems.append(f"{here}.index: a word number 1, 2, … or -1 (the last word)")
    return problems


def is_word(value) -> bool:
    return isinstance(value, dict) and "word" in value


def _set_word_problems(rule, here) -> list:
    extra = [k for k in rule if k not in ("set", "comment")]
    problems = [f"{here}: unknown key {k!r}" for k in extra]
    body, where = rule["set"], f"{here}.set"
    problems += S._keys_problems(body, where, ("var", "value"), ("flavor", "export"))
    if problems:
        return problems
    problems += S._name_problems(body["var"], f"{where}.var")
    problems += word_problems(body["value"], f"{where}.value")
    if body.get("flavor", "recursive") not in S.FLAVORS:
        problems.append(f"{where}.flavor: one of {', '.join(S.FLAVORS)}")
    if "export" in body and body["export"] is not True:
        problems.append(f"{where}.export: must be true")
    return problems


def rules_problems(rules, where="rules") -> list:
    """Problems of a rule list of this step: the flash rule language
    (flashdata.rules_problems) plus `command: {name}` and `word`."""
    if not isinstance(rules, list):
        return [f"{where}: must be a list"]
    problems = []
    for i, rule in enumerate(rules):
        here = f"{where}[{i}]"
        if isinstance(rule, dict) and any(k in rule for k in NOT_IN_DATA):
            problems.append(f"{here}: `section` is build data only")
        elif isinstance(rule, dict) and "if" in rule:
            problems += condition_problems(rule["if"], f"{here}.if")
            if "then" not in rule:
                problems.append(f"{here}: if without then")
            unknown = [k for k in rule if k not in ("if", "then", "elif", "else", "comment")]
            problems += [f"{here}: unknown key {k!r}" for k in unknown]
            for branch in ("then", "else"):
                if branch in rule:
                    problems += rules_problems(rule[branch], f"{here}.{branch}")
            elifs = rule.get("elif")
            if "elif" in rule and (not isinstance(elifs, list) or not elifs):
                problems.append(f"{here}.elif: must be a non-empty list")
            for j, branch in enumerate(elifs if isinstance(elifs, list) else []):
                bhere = f"{here}.elif[{j}]"
                problems += S._keys_problems(branch, bhere, ("if", "then"), ("comment",))
                if isinstance(branch, dict) and "if" in branch and "then" in branch:
                    problems += condition_problems(branch["if"], f"{bhere}.if")
                    problems += rules_problems(branch["then"], f"{bhere}.then")
        elif isinstance(rule, dict) and isinstance(rule.get("set"), dict) \
                and is_word(rule["set"].get("value")):
            problems += _set_word_problems(rule, here)
        else:
            problems += F.rules_problems([rule], here)
    return problems


def validate(document) -> list:
    """Problems of a whole data document (empty: valid)."""
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
    """The rules of a data file; ValueError with its problems."""
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
    if key == "command" and "name" in value:
        kind = "ifeq" if negated else "ifneq"
        return f"{kind} (,$(shell command -v {value['name']} 2>/dev/null))"
    return F.condition_text(cond)


def word_text(value: dict) -> str:
    body = value["word"]
    if body["index"] == 1:
        return f"$(firstword $({body['var']}))"
    if body["index"] == -1:
        return f"$(lastword $({body['var']}))"
    return f"$(word {body['index']},$({body['var']}))"


def _set_word(rule: dict, pad: str) -> str:
    body = rule["set"]
    op = {"recursive": "=", "simple": ":=", "conditional": "?="}[body.get("flavor", "recursive")]
    export = "export " if body.get("export") else ""
    return f"{pad}{export}{body['var']} {op} {word_text(body['value'])}"


def _if(rule: dict, depth: int) -> list:
    pad = "  " * depth
    out = [pad + condition_text(rule["if"])]
    out += lines(rule.get("then") or [], depth + 1)
    for branch in rule.get("elif") or []:
        if "comment" in branch:
            out += G._comment(branch["comment"], pad)
        out.append(f"{pad}else {condition_text(branch['if'])}")
        out += lines(branch.get("then") or [], depth + 1)
    if "else" in rule:
        out.append(pad + "else")
        out += lines(rule["else"], depth + 1)
    out.append(pad + "endif")
    return out


def lines(rules: list, depth: int = 0) -> list:
    """Make lines of a rule list (the layout of the flash and configuration
    data generators; `if` and `word` here, every other rule there)."""
    pad = "  " * depth
    out = []
    previous = None
    for rule in rules:
        if depth == 0 and previous is not None and G._paragraph(rule, previous):
            out.append("")
        if "comment" in rule:
            out += G._comment(rule["comment"], pad)
        if "if" in rule:
            out += _if(rule, depth)
        elif isinstance(rule.get("set"), dict) and is_word(rule["set"].get("value")):
            out.append(_set_word(rule, pad))
        elif set(rule) != {"comment"}:
            out += F.lines([{k: v for k, v in rule.items() if k != "comment"}], depth)
        previous = rule
    return out


def make_text(rules: list, data_base: str) -> str:
    head = [f"# Generated from {data_base} by dist/tools/term/term.py.",
            f"# Do not edit: change {data_base} and run `just generate-term-data`.", ""]
    return "\n".join(head + lines(G.for_make(rules))) + "\n"


def expected_adapter(path: str) -> str:
    return make_text(load(path), os.path.basename(path))
