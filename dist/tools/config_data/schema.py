# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Validator of the configuration data format (schema 1, see README.md).

validate(document) returns a list of problems, each one with the path of
the offending value (e.g. `rules[3].then[0].if.has.match[1]`); an empty list
means the document is valid. Every condition and action is structured:
the only reference to another value is `${NAME}` in a text, and no Make
function or other Make syntax is accepted.
"""

import re

from rules import NAME_RE, REF_RE, SCHEMA

ACTIONS = ("if", "add", "set", "include", "error", "warning", "info")
CONDITIONS = ("has", "selection_equals", "one_of", "equals", "not")
BRANCHES = ("then", "elif", "else")
FLAVORS = ("recursive", "simple", "conditional")
# a word of a filter pattern: no blank, no `$`, `,`, `(`, `)`, `#`, at most one `%`
PATTERN_RE = re.compile(r"^[^\s$(),#%]*%?[^\s$(),#%]*$")
# a literal word compared with a value: like a pattern, without `%`
WORD_RE = re.compile(r"^[^\s$(),#%]+$")


def _text_problems(text, where, allow_blank=True, allow_percent=True,
                   balanced=False):
    if not isinstance(text, str):
        return [f"{where}: must be a string"]
    problems = []
    rest = REF_RE.sub("", text)
    if "$" in rest:
        problems.append(f"{where}: `$` is only allowed in a reference ${{NAME}}")
    if "#" in text:
        problems.append(f"{where}: `#` is not allowed")
    if "\n" in text:
        problems.append(f"{where}: must be one line")
    if not allow_blank and (not text or any(c.isspace() for c in text)):
        problems.append(f"{where}: must be one non-empty word")
    if not allow_percent and "%" in text:
        problems.append(f"{where}: `%` is not allowed")
    if balanced:
        depth = 0
        for char in rest:
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth < 0:
                break
        if depth != 0:
            problems.append(f"{where}: parentheses must be balanced")
    return problems


def _name_problems(name, where):
    if not isinstance(name, str) or not NAME_RE.match(name):
        return [f"{where}: {name!r} is not a variable name"]
    return []


def _words_problems(words, where, regex, what):
    if not isinstance(words, list) or not words:
        return [f"{where}: must be a non-empty list"]
    return [f"{where}[{i}]: {w!r} is not a {what}" for i, w in enumerate(words)
            if not isinstance(w, str) or not regex.match(w)]


def _keys_problems(value, where, required, optional=()):
    if not isinstance(value, dict):
        return [f"{where}: must be a mapping"]
    problems = [f"{where}: missing key {k!r}" for k in required if k not in value]
    problems += [f"{where}: unknown key {k!r}" for k in value
                 if k not in required and k not in optional]
    return problems


def _selection_problems(value, where, extra=()):
    problems = _keys_problems(value, where, ("var", "match") + tuple(extra), ("except",))
    if problems:
        return problems
    problems += _name_problems(value["var"], f"{where}.var")
    problems += _words_problems(value["match"], f"{where}.match", PATTERN_RE, "pattern")
    if "except" in value:
        problems += _words_problems(value["except"], f"{where}.except", PATTERN_RE, "pattern")
    return problems


def condition_problems(cond, where, negated=False):
    if not isinstance(cond, dict) or len(cond) != 1:
        return [f"{where}: a condition is a mapping with one of {', '.join(CONDITIONS)}"]
    (key, value), = cond.items()
    where = f"{where}.{key}"
    if key == "not":
        if negated:
            return [f"{where}: `not` inside `not`; write the condition itself"]
        return condition_problems(value, where, negated=True)
    if key == "has":
        return _selection_problems(value, where)
    if key == "selection_equals":
        problems = _selection_problems(value, where, ("words",))
        if not problems:
            problems += _words_problems(value["words"], f"{where}.words", WORD_RE, "word")
        return problems
    if key == "one_of":
        problems = _keys_problems(value, where, ("var", "values"))
        if not problems:
            problems += _name_problems(value["var"], f"{where}.var")
            problems += _words_problems(value["values"], f"{where}.values", WORD_RE, "word")
        return problems
    if key == "equals":
        if not isinstance(value, dict) or not value:
            return [f"{where}: must be a non-empty mapping VAR: value"]
        problems = []
        for var, val in value.items():
            problems += _name_problems(var, f"{where}.{var}")
            if not isinstance(val, str):
                problems.append(f"{where}.{var}: must be a string")
            elif len(value) > 1 and not WORD_RE.match(val):
                problems.append(f"{where}.{var}: with several variables each value "
                                "must be one non-empty word")
            elif val and not WORD_RE.match(val.replace(" ", "x")):
                problems.append(f"{where}.{var}: {val!r} is not a literal value")
        return problems
    return [f"{where}: unknown condition (one of {', '.join(CONDITIONS)})"]


def _action_problems(rule, key, where):
    value = rule[key]
    where = f"{where}.{key}"
    if key == "add":
        if not isinstance(value, dict) or len(value) != 1:
            return [f"{where}: must be a mapping with one variable"]
        (var, items), = value.items()
        problems = _name_problems(var, f"{where}.{var}")
        if not isinstance(items, list) or not items:
            return problems + [f"{where}.{var}: must be a non-empty list"]
        for i, item in enumerate(items):
            problems += _text_problems(item, f"{where}.{var}[{i}]")
            if isinstance(item, str) and not item.strip():
                problems.append(f"{where}.{var}[{i}]: must not be empty")
        return problems
    if key == "set":
        problems = _keys_problems(value, where, ("var", "value"), ("flavor",))
        if problems:
            return problems
        problems += _name_problems(value["var"], f"{where}.var")
        problems += _text_problems(value["value"], f"{where}.value")
        if value.get("flavor", "recursive") not in FLAVORS:
            problems.append(f"{where}.flavor: one of {', '.join(FLAVORS)}")
        return problems
    if key == "include":
        problems = _keys_problems(value, where, ("path",), ("optional", "for_each", "sort"))
        if problems:
            return problems
        path = value["path"]
        problems += _text_problems(path, f"{where}.path", allow_blank=False)
        for flag in ("optional", "sort"):
            if flag in value and not isinstance(value[flag], bool):
                problems.append(f"{where}.{flag}: must be true or false")
        if "for_each" in value:
            problems += _name_problems(value["for_each"], f"{where}.for_each")
            if isinstance(path, str) and path.count("%") != 1:
                problems.append(f"{where}.path: needs exactly one `%` (the word of for_each)")
        else:
            if "sort" in value:
                problems.append(f"{where}.sort: only with for_each")
            if isinstance(path, str) and "%" in path:
                problems.append(f"{where}.path: `%` only with for_each")
        return problems
    # error, warning, info
    problems = _text_problems(value, where, balanced=True)
    if isinstance(value, str) and not value.strip():
        problems.append(f"{where}: must not be empty")
    return problems


def _elif_problems(branches, where):
    if not isinstance(branches, list) or not branches:
        return [f"{where}: must be a non-empty list"]
    problems = []
    for i, branch in enumerate(branches):
        here = f"{where}[{i}]"
        problems += _keys_problems(branch, here, ("if", "then"), ("comment",))
        if isinstance(branch, dict) and "if" in branch and "then" in branch:
            problems += condition_problems(branch["if"], f"{here}.if")
            problems += rules_problems(branch["then"], f"{here}.then")
            if "comment" in branch and not isinstance(branch["comment"], str):
                problems.append(f"{here}.comment: must be a string")
    return problems


def rules_problems(rules, where="rules"):
    if not isinstance(rules, list):
        return [f"{where}: must be a list"]
    problems = []
    for i, rule in enumerate(rules):
        here = f"{where}[{i}]"
        if not isinstance(rule, dict):
            problems.append(f"{here}: must be a mapping")
            continue
        if "comment" in rule and not isinstance(rule["comment"], str):
            problems.append(f"{here}.comment: must be a string")
        actions = [k for k in rule if k in ACTIONS]
        unknown = [k for k in rule if k not in ACTIONS + ("comment",) + BRANCHES]
        problems += [f"{here}: unknown key {k!r}" for k in unknown]
        if len(actions) > 1:
            problems.append(f"{here}: more than one action ({', '.join(actions)})")
            continue
        if not actions:
            if "comment" not in rule:
                problems.append(f"{here}: no action (one of {', '.join(ACTIONS)})")
            if any(b in rule for b in BRANCHES):
                problems.append(f"{here}: then/elif/else only with if")
            continue
        key = actions[0]
        if key == "if":
            problems += condition_problems(rule["if"], f"{here}.if")
            if "then" not in rule:
                problems.append(f"{here}: if without then")
            for branch in ("then", "else"):
                if branch in rule:
                    problems += rules_problems(rule[branch], f"{here}.{branch}")
            if "elif" in rule:
                problems += _elif_problems(rule["elif"], f"{here}.elif")
        else:
            if any(b in rule for b in BRANCHES):
                problems.append(f"{here}: then/elif/else only with if")
            problems += _action_problems(rule, key, here)
    return problems


def validate(document) -> list:
    """Problems of a whole YAML document (empty list: valid)."""
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
