# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Generator: rule list -> Make file (the transitional adapter for Make).

The output is plain Make that GNU Make reads exactly like the original
file; it is checked in next to the YAML and must never be edited by hand.
Layout: two spaces per nesting level, `elif` as `else ifeq`, one
`VAR += item` line per item (RIOT's style).

The `several` condition is written with `_is_greater` of RIOT's string
helpers, so a file that uses it starts with the include of
`makefiles/utils/strings.mk` (as the original `stdio.inc.mk` did).
"""

from rules import to_make_text, uses_several

STRING_HELPERS = "include $(RIOTMAKE)/utils/strings.mk"

def header(yaml_base: str) -> list:
    return [f"# Generated from {yaml_base} by dist/tools/config_data/config_data.py.",
            f"# Do not edit: change {yaml_base} and run `just generate-config-data`.",
            ""]


def _patterns(words: list) -> str:
    return " ".join(to_make_text(w) for w in words)


def _selection(sel: dict) -> str:
    words = f"$({sel['var']})"
    if sel.get("except"):
        words = f"$(filter-out {_patterns(sel['except'])},{words})"
    if sel.get("match"):
        words = f"$(filter {_patterns(sel['match'])},{words})"
    return words


def value_text(value) -> str:
    """Make text of a value: a text or `{select: …}` (schema 2)."""
    if not isinstance(value, dict):
        return to_make_text(value)
    sel = value["select"]
    text = _selection(sel)
    if "replace" in sel:
        text = f"$(subst {sel['replace']['from']},{sel['replace']['to']},{text})"
    return text


def condition(cond: dict) -> str:
    """`ifeq (…)` / `ifneq (…)` of a condition."""
    (key, value), = cond.items()
    negated = key == "not"
    if negated:
        (key, value), = value.items()
    if key == "has":
        kind, args = "ifneq", f",{_selection(value)}"
    elif key == "one_of":
        kind, args = "ifneq", f",$(filter $({value['var']}),{' '.join(value['values'])})"
    elif key == "selection_equals":
        kind, args = "ifeq", f"{' '.join(value['words'])},{_selection(value)}"
    elif key == "several":
        kind, args = "ifeq", f"1,$(call _is_greater,$(words $(sort {_selection(value)})),1)"
    elif key == "equals":
        refs = " ".join(f"$({var})" for var in value)
        kind, args = "ifeq", f"{refs},{' '.join(value.values())}"
    else:
        raise ValueError(f"unknown condition {key}")
    if negated:
        kind = "ifeq" if kind == "ifneq" else "ifneq"
    return f"{kind} ({args})"


def _include(inc: dict) -> str:
    path = to_make_text(inc["path"])
    if "for_each" in inc:
        path = f"$({inc['for_each']}:%={path})"
        if inc.get("sort"):
            path = f"$(sort {path})"
    return ("-include " if inc.get("optional") else "include ") + path


def _action(rule: dict, pad: str) -> list:
    if "add" in rule:
        (var, items), = rule["add"].items()
        # one line per item, as RIOT writes them
        return [f"{pad}{var} += {value_text(item)}" for item in items]
    if "set" in rule:
        op = {"recursive": "=", "simple": ":=", "conditional": "?="}[
            rule["set"].get("flavor", "recursive")]
        return [f"{pad}{rule['set']['var']} {op} {value_text(rule['set']['value'])}".rstrip()]
    if "include" in rule:
        return [pad + _include(rule["include"])]
    for level in ("error", "warning", "info"):
        if level in rule:
            return [f"{pad}$({level} {to_make_text(rule[level])})"]
    raise ValueError(f"unknown rule {sorted(rule)}")


def _comment(text: str, pad: str) -> list:
    return [f"{pad}# {line}" if line else f"{pad}#" for line in text.split("\n")]


def _if(rule: dict, depth: int) -> list:
    pad = "  " * depth
    out = [pad + condition(rule["if"])]
    out += lines(rule.get("then") or [], depth + 1)
    for branch in rule.get("elif") or []:
        if "comment" in branch:
            out += _comment(branch["comment"], pad)
        out.append(f"{pad}else {condition(branch['if'])}")
        out += lines(branch.get("then") or [], depth + 1)
    if "else" in rule:
        out.append(pad + "else")
        out += lines(rule["else"], depth + 1)
    out.append(pad + "endif")
    return out


def _paragraph(rule: dict, previous: dict) -> bool:
    """At the top level, a blank line goes before a conditional or a
    commented rule and after a conditional or a standalone comment."""
    return ("if" in rule or "comment" in rule or "if" in previous
            or set(previous) == {"comment"})


def lines(rules: list, depth: int = 0) -> list:
    pad = "  " * depth
    out = []
    previous = None
    for rule in rules:
        if depth == 0 and previous is not None and _paragraph(rule, previous):
            out.append("")
        if "comment" in rule:
            out += _comment(rule["comment"], pad)
        if "if" in rule:
            out += _if(rule, depth)
        elif set(rule) != {"comment"}:
            out += _action(rule, pad)
        previous = rule
    return out


def make_text(rules: list, yaml_base: str) -> str:
    """The whole generated Make file."""
    helpers = [STRING_HELPERS, ""] if uses_several(rules) else []
    return "\n".join(header(yaml_base) + helpers + lines(rules)) + "\n"
