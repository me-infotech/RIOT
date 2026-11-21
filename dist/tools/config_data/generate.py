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

Step G0-3: build and package data (schema 4). A data file describes either
a whole Make file (it is generated as that file) or a part of one: then the
generated file is `<data name>.mk` and the Make file includes it where the
part was. A part that is not contiguous in the Make file is split into
`section`s; the Make file includes the generated file once per section,
with RIOT_BUILD_SECTION set to the section's name. Rules with `stand_in`
are left out: they stand for what the named Make file still does itself.
"""

import re

from rules import REF_RE, to_make_text, uses_several

SECTION_VAR = "RIOT_BUILD_SECTION"
STAND_IN = "stand_in"

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


class NotForMake(ValueError):
    """A construct that has no Make text in this place (`once` outside a
    `set`)."""


def _select_text(sel: dict) -> str:
    text = _selection(sel)
    if sel.get("unique"):
        # `uniq` of Makefile.include: duplicates removed, first one kept
        text = f"$(strip $(call uniq,{text}))"
    if "replace" in sel:
        text = f"$(subst {sel['replace']['from']},{sel['replace']['to']},{text})"
    if sel.get("macro"):
        text = f"$(call uppercase_and_underscore,{text})"
    if "pattern" in sel:
        pat = sel["pattern"]
        text = f"$(patsubst {to_make_text(pat['from'])},{to_make_text(pat['to'])},{text})"
    return text


def _arith_text(arith: dict, var: str = None) -> str:
    """`$((…))` of the shell, as RIOT's Make files compute it: a variable may
    hold `NK` (N*1024), as `$(V:%K=%*1024)` - every variable, or with `kilo`
    (schema 4) only those named there, the others as `$(V)`; `once`:
    memoized (expanded once, makefiles/utils/variables.mk)."""
    kilo = arith.get("kilo")
    expr = REF_RE.sub(lambda m: f"$({m.group(1)}:%K=%*1024)"
                      if kilo is None or m.group(1) in kilo else f"$({m.group(1)})",
                      arith["expr"])
    expr = re.sub(r"\b([0-9]+)K\b", r"\1*1024", expr)
    if arith.get("format") == "hex":
        text = f'$(shell printf "0x%x" $$(({expr})))'
    else:
        text = f"$(shell echo $$(({expr})))"
    if arith.get("once"):
        if var is None:
            raise NotForMake("`once` only as the value of a `set`")
        text = f"$(call memoized,{var},{text})"
    return text


def value_text(value, var: str = None) -> str:
    """Make text of a value: a text, `{select: …}` (schema 2), `{files: …}`,
    `{subdirs: …}`, `{arith: …}` (schema 3) or `{when: …}` (schema 4); `var`
    is the variable a `set` assigns."""
    if not isinstance(value, dict):
        return to_make_text(value)
    if "files" in value:
        files = value["files"]
        text = f"$(wildcard {_patterns(files['match'])})"
        if files.get("except"):
            text = f"$(filter-out {_patterns(files['except'])},{text})"
        if files.get("sort"):
            text = f"$(sort {text})"
        return text
    if "when" in value:
        when = value["when"]
        text = f"$(if {_selection(when['test'])},{to_make_text(when.get('then', ''))}"
        if "else" in when:
            text += f",{to_make_text(when['else'])}"
        return text + ")"
    if "subdirs" in value:
        sub = value["subdirs"]
        return f"$(dir $(wildcard $(addsuffix /{sub['file']},{_select_text(sub['select'])})))"
    if "arith" in value:
        return _arith_text(value["arith"], var)
    return _select_text(value["select"])


def condition(cond: dict) -> str:
    """`ifeq (…)` / `ifneq (…)` of a condition."""
    (key, value), = cond.items()
    negated = key == "not"
    if negated:
        (key, value), = value.items()
    if key == "defined":
        return f"{'ifndef' if negated else 'ifdef'} {value}"
    if key == "count":
        return f"{'ifneq' if negated else 'ifeq'} ({value['is']},$(words {_selection(value)}))"
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
    elif key == "at_least":
        kind = "ifeq"
        args = f"1,$(call version_is_greater_or_equal,$({value['var']}),{value['version']})"
    elif key == "nonempty":
        kind, args = "ifneq", "," + "".join(f"$({var})" for var in value)
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
        var = rule["set"]["var"]
        export = "export " if rule["set"].get("export") else ""
        text = f"{pad}{export}{var} {op} {value_text(rule['set']['value'], var)}"
        return [text if _trailing_blanks(rule) else text.rstrip()]
    for kind in ("export", "unexport"):
        if kind in rule:
            return [f"{pad}{kind} {name}" for name in rule[kind]]
    if "include" in rule:
        return [pad + _include(rule["include"])]
    for level in ("error", "warning", "info"):
        if level in rule:
            return [f"{pad}$({level} {to_make_text(rule[level])})"]
    raise ValueError(f"unknown rule {sorted(rule)}")


def _comment(text: str, pad: str) -> list:
    """`# text`; a line that starts with `#` is a Doxygen line (`## text`)."""
    return [f"{pad}#{line}" if line.startswith("#") else f"{pad}# {line}" if line
            else f"{pad}#" for line in text.split("\n")]


def for_make(rules: list) -> list:
    """The rules without `stand_in` rules (in every branch)."""
    out = []
    for rule in rules:
        if STAND_IN in rule:
            continue
        if "if" in rule:
            rule = dict(rule)
            for key in ("then", "else"):
                if key in rule:
                    rule[key] = for_make(rule[key])
            if "elif" in rule:
                rule["elif"] = [{**b, "then": for_make(b.get("then") or [])}
                                for b in rule["elif"]]
        out.append(rule)
    return out


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
        if _trailing_blanks(rule):
            # Make keeps the blanks before a comment in the value: the only
            # way to write a value that ends with blanks (schema 4)
            if "\n" in rule.get("comment", "\n"):
                raise NotForMake(f"{rule['set']['var']}: a value that ends with blanks needs "
                                 "a one-line comment after it")
            out.append(_action(rule, pad)[0] + "# " + rule["comment"])
            previous = rule
            continue
        if "comment" in rule:
            out += _comment(rule["comment"], pad)
        if "if" in rule:
            out += _if(rule, depth)
        elif set(rule) != {"comment"}:
            out += _action(rule, pad)
        previous = rule
    return out


def _trailing_blanks(rule: dict) -> bool:
    value = rule.get("set", {}).get("value")
    return isinstance(value, str) and value != value.rstrip()


def make_text(rules: list, yaml_base: str, part_of: str = None) -> str:
    """The whole generated Make file; `part_of`: the Make file that includes
    it (build data that describes a part of a Make file)."""
    rules = for_make(rules)
    head = header(yaml_base)
    sections = [r["section"] for r in rules if "section" in r]
    if part_of and sections:
        head[-1:] = [f"# The build part of {part_of}, which includes this file once per",
                     f"# section with {SECTION_VAR} set to the name of the section.", ""]
        return "\n".join(head + _sections(rules, part_of)) + "\n"
    if part_of:
        head[-1:] = [f"# The build part of {part_of}, which includes this file.", ""]
    helpers = [STRING_HELPERS, ""] if uses_several(rules) else []
    return "\n".join(head + helpers + lines(rules)) + "\n"


def _sections(rules: list, part_of: str) -> list:
    """One `ifeq` block per section; the block clears the selection, so a
    section of another generated file included inside it is not mistaken
    for one of this file. A name without a block stops Make."""
    out, groups = [], []
    for rule in rules:
        if "section" in rule:
            groups.append((rule, []))
        elif groups:
            groups[-1][1].append(rule)
    for mark, body in groups:
        if "comment" in mark:
            out += _comment(mark["comment"], "")
        out.append(f"ifeq ({mark['section']},$({SECTION_VAR}))")
        out.append(f"  {SECTION_VAR} :=")
        if uses_several(body):
            out.append("  " + STRING_HELPERS)
        out += lines(body, 1)
        out += ["endif", ""]
    out += [f"ifneq (,$({SECTION_VAR}))",
            f"  $(error {part_of}: no build section $({SECTION_VAR}))", "endif"]
    return out
