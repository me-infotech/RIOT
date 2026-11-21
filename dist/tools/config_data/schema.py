# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Validator of the configuration data format (schemas 1 and 2, see README.md).

validate(document) returns a list of problems, each one with the path of
the offending value (e.g. `rules[3].then[0].if.has.match[1]`); an empty list
means the document is valid. Every condition and action is structured:
the only reference to another value is `${NAME}` in a text, and no Make
function or other Make syntax is accepted. Schema 2 adds `select` values,
`${NAME}` as a whole pattern word and the `several` condition. Schema 3
(step G3-1) adds the values `files`, `subdirs` and `arith`, `pattern`,
`macro` and `unique` in a selection and the conditions `at_least` and
`nonempty`. Schema 4 (step G0-3) adds the `section` and `stand_in` rules,
`export` (a rule, and a flag of `set`), `unexport`, the value `when`, `sort` of `files`,
`once` and `kilo` of `arith` and the conditions `defined` and `count`.
"""

import re

from rules import NAME_RE, REF_RE, SCHEMAS, needed_schema

ACTIONS = ("if", "add", "set", "include", "error", "warning", "info", "export", "unexport",
           "section")
CONDITIONS = ("has", "selection_equals", "one_of", "equals", "several", "at_least",
              "nonempty", "defined", "count", "not")
# schema 4: a key of any rule - the rule is read by the build without Make
# only; it stands for what the named Make file still does itself (the
# generated Make leaves it out)
STAND_IN = "stand_in"
STAND_IN_RE = re.compile(r"^[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*$")
BRANCHES = ("then", "elif", "else")
FLAVORS = ("recursive", "simple", "conditional")
# a word of a filter pattern: no blank, no `$`, `,`, `(`, `)`, `#`, at most one `%`
PATTERN_RE = re.compile(r"^[^\s$(),#%]*%?[^\s$(),#%]*$")
# schema 2: a pattern word may also be `${NAME}` (the words of NAME)
PATTERN2_RE = re.compile(r"^(?:[^\s$(),#%]*%?[^\s$(),#%]*|\$\{[A-Za-z_][A-Za-z0-9_]*\})$")
# a literal word compared with a value: like a pattern, without `%`
WORD_RE = re.compile(r"^[^\s$(),#%]+$")
# the text `replace` changes in each selected word: no blank, `$`, `,`, `(`, `)`, `#`, `%`
REPLACE_RE = re.compile(r"^[^\s$(),#%]*$")
# schema 3: a word of a pattern substitution (`%` at most once, `${NAME}` allowed)
PATSUBST_RE = re.compile(r"^(?:[^\s$(),#%]|\$\{[A-Za-z_][A-Za-z0-9_]*\})*"
                         r"%?(?:[^\s$(),#%]|\$\{[A-Za-z_][A-Za-z0-9_]*\})*$")
# schema 3: a file name pattern of `files` (`*`, `?`, `${NAME}`; no blank)
GLOB_RE = re.compile(r"^(?:[^\s$(),#%]|\$\{[A-Za-z_][A-Za-z0-9_]*\})+$")
# schema 3: an arithmetic expression of `arith`: integers, `${NAME}`, + - * ( ), `K`
ARITH_RE = re.compile(r"^(?:[0-9a-fA-FxK+\-* ()]|\$\{[A-Za-z_][A-Za-z0-9_]*\})+$")
NAME_WORD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")


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
    problems += _words_problems(value["match"], f"{where}.match", PATTERN2_RE, "pattern")
    if "except" in value:
        problems += _words_problems(value["except"], f"{where}.except", PATTERN2_RE, "pattern")
    return problems


def select_problems(value, where):
    """`{select: {var, match?, except?, replace?: {from, to}}}` (schema 2):
    the words of var that match and are not excepted, each with `from`
    replaced by `to`."""
    problems = _keys_problems(value, where, ("select",))
    if problems:
        return problems
    sel, where = value["select"], f"{where}.select"
    problems = _keys_problems(sel, where, ("var",), ("match", "except", "replace", "pattern",
                                                     "macro", "unique"))
    if problems:
        return problems
    problems += _name_problems(sel["var"], f"{where}.var")
    for key in ("match", "except"):
        if key in sel:
            problems += _words_problems(sel[key], f"{where}.{key}", PATTERN2_RE, "pattern")
    if "replace" in sel:
        rep = sel["replace"]
        here = f"{where}.replace"
        problems += _keys_problems(rep, here, ("from", "to"))
        if not problems:
            for key in ("from", "to"):
                if not isinstance(rep[key], str) or not REPLACE_RE.match(rep[key]):
                    problems.append(f"{here}.{key}: {rep[key]!r} is not a literal text")
            if rep["from"] == "":
                problems.append(f"{here}.from: must not be empty")
    if "pattern" in sel:
        here = f"{where}.pattern"
        pat = sel["pattern"]
        problems += _keys_problems(pat, here, ("from", "to"))
        if not _keys_problems(pat, here, ("from", "to")):
            for key in ("from", "to"):
                if not isinstance(pat[key], str) or not PATSUBST_RE.match(pat[key]):
                    problems.append(f"{here}.{key}: {pat[key]!r} is not a pattern word")
            if isinstance(pat["from"], str) and pat["from"].count("%") != 1:
                problems.append(f"{here}.from: needs exactly one `%`")
    for flag in ("macro", "unique"):
        if flag in sel and not isinstance(sel[flag], bool):
            problems.append(f"{where}.{flag}: must be true or false")
    return problems


def value_problems(value, where):
    """A value of `set` or an item of `add`: a text or one of the structured
    values (`select`; schema 3: `files`, `subdirs`, `arith`)."""
    if not isinstance(value, dict):
        problems = _text_problems(value, where)
        return problems
    if len(value) != 1:
        return [f"{where}: a structured value has exactly one key"]
    (key, body), = value.items()
    if key == "select":
        return select_problems(value, where)
    here = f"{where}.{key}"
    if key == "files":
        problems = _keys_problems(body, here, ("match",), ("except", "sort"))
        if not problems:
            if "sort" in body and not isinstance(body["sort"], bool):
                problems.append(f"{here}.sort: must be true or false")
            problems += _words_problems(body["match"], f"{here}.match", GLOB_RE, "file pattern")
            if "except" in body:
                problems += _words_problems(body["except"], f"{here}.except", PATTERN2_RE,
                                            "pattern")
        return problems
    if key == "subdirs":
        problems = _keys_problems(body, here, ("select", "file"))
        if not problems:
            problems += select_problems({"select": body["select"]}, here)
            if not isinstance(body["file"], str) or not WORD_RE.match(body["file"]) \
                    or "/" in body["file"]:
                problems.append(f"{here}.file: must be a file name")
        return problems
    if key == "arith":
        problems = _keys_problems(body, here, ("expr",), ("format", "once", "kilo"))
        if not problems:
            if "kilo" in body:
                problems += _words_problems(body["kilo"], f"{here}.kilo", NAME_WORD_RE,
                                            "variable name")
                refs = REF_RE.findall(body["expr"]) if isinstance(body["expr"], str) else []
                problems += [f"{here}.kilo: {n!r} is not used in expr"
                             for n in body["kilo"] if isinstance(n, str) and n not in refs]
            if "once" in body and not isinstance(body["once"], bool):
                problems.append(f"{here}.once: must be true or false")
            if not isinstance(body["expr"], str) or not ARITH_RE.match(body["expr"]):
                problems.append(f"{here}.expr: {body['expr']!r} is not an expression")
            if body.get("format", "dec") not in ("dec", "hex"):
                problems.append(f"{here}.format: dec or hex")
        return problems
    if key == "when":
        problems = _keys_problems(body, here, ("test",), ("then", "else"))
        if not problems:
            problems += _keys_problems(body["test"], f"{here}.test", ("var",),
                                       ("match", "except"))
        if not problems:
            sel = body["test"]
            problems += _name_problems(sel["var"], f"{here}.test.var")
            for key2 in ("match", "except"):
                if key2 in sel:
                    problems += _words_problems(sel[key2], f"{here}.test.{key2}", PATTERN2_RE,
                                                "pattern")
            for branch in ("then", "else"):
                if branch in body:
                    problems += _text_problems(body[branch], f"{here}.{branch}", balanced=True)
                    if isinstance(body[branch], str) and "," in body[branch]:
                        problems.append(f"{here}.{branch}: `,` is not allowed")
        return problems
    return [f"{where}: unknown value {key!r} (select, files, subdirs, arith, when)"]


def condition_problems(cond, where, negated=False):
    if not isinstance(cond, dict) or len(cond) != 1:
        return [f"{where}: a condition is a mapping with one of {', '.join(CONDITIONS)}"]
    (key, value), = cond.items()
    where = f"{where}.{key}"
    if key == "not":
        if negated:
            return [f"{where}: `not` inside `not`; write the condition itself"]
        return condition_problems(value, where, negated=True)
    if key in ("has", "several"):
        return _selection_problems(value, where)
    if key == "selection_equals":
        problems = _selection_problems(value, where, ("words",))
        if not problems:
            problems += _words_problems(value["words"], f"{where}.words", WORD_RE, "word")
        return problems
    if key == "at_least":
        problems = _keys_problems(value, where, ("var", "version"))
        if not problems:
            problems += _name_problems(value["var"], f"{where}.var")
            if not isinstance(value["version"], str) or not VERSION_RE.match(value["version"]):
                problems.append(f"{where}.version: a version like 8 or 4.2.1")
        return problems
    if key == "defined":
        return _name_problems(value, where)
    if key == "count":
        problems = _keys_problems(value, where, ("var", "is"), ("match", "except"))
        if not problems:
            problems += _name_problems(value["var"], f"{where}.var")
            for key2 in ("match", "except"):
                if key2 in value:
                    problems += _words_problems(value[key2], f"{where}.{key2}", PATTERN2_RE,
                                                "pattern")
            if not isinstance(value["is"], int) or isinstance(value["is"], bool) \
                    or value["is"] < 0:
                problems.append(f"{where}.is: must be a number of words (0, 1, …)")
        return problems
    if key == "nonempty":
        if not isinstance(value, list) or not value:
            return [f"{where}: must be a non-empty list of variable names"]
        problems = []
        for i, name in enumerate(value):
            problems += _name_problems(name, f"{where}[{i}]")
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
            if isinstance(item, dict):
                problems += value_problems(item, f"{where}.{var}[{i}]")
                continue
            problems += _text_problems(item, f"{where}.{var}[{i}]")
            if isinstance(item, str) and not item.strip():
                problems.append(f"{where}.{var}[{i}]: must not be empty")
        return problems
    if key == "set":
        problems = _keys_problems(value, where, ("var", "value"), ("flavor", "export"))
        if problems:
            return problems
        if "export" in value and value["export"] is not True:
            problems.append(f"{where}.export: must be true")
        problems += _name_problems(value["var"], f"{where}.var")
        if isinstance(value["value"], dict):
            problems += value_problems(value["value"], f"{where}.value")
        else:
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
    if key in ("export", "unexport"):
        if not isinstance(value, list) or not value:
            return [f"{where}: must be a non-empty list of variable names"]
        problems = []
        for i, name in enumerate(value):
            problems += _name_problems(name, f"{where}[{i}]")
        return problems
    if key == "section":
        if not isinstance(value, str) or not re.match(r"^[a-z][a-z0-9_]*$", value):
            return [f"{where}: {value!r} is not a section name (a-z, 0-9, _)"]
        return []
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
            problems += rules_problems(branch["then"], f"{here}.then", top=False)
            if "comment" in branch and not isinstance(branch["comment"], str):
                problems.append(f"{here}.comment: must be a string")
    return problems


def _sections_problems(rules) -> list:
    """`section` rules: only at the top level; once a file uses them, every
    rule follows one (only comments may stand before the first), and no
    name is used twice."""
    marks = [i for i, r in enumerate(rules) if isinstance(r, dict) and "section" in r]
    if not marks:
        return []
    problems = [f"rules[{i}]: before the first section" for i, r in enumerate(rules[:marks[0]])
                if not isinstance(r, dict) or set(r) != {"comment"}]
    names = [rules[i]["section"] for i in marks]
    problems += [f"rules[{i}].section: {rules[i]['section']!r} is used twice"
                 for n, i in enumerate(marks) if rules[i]["section"] in names[:n]]
    return problems


def rules_problems(rules, where="rules", top=True):
    if not isinstance(rules, list):
        return [f"{where}: must be a list"]
    problems = _sections_problems(rules) if top else []
    for i, rule in enumerate(rules):
        here = f"{where}[{i}]"
        if not isinstance(rule, dict):
            problems.append(f"{here}: must be a mapping")
            continue
        if "comment" in rule and not isinstance(rule["comment"], str):
            problems.append(f"{here}.comment: must be a string")
        if STAND_IN in rule and (not isinstance(rule[STAND_IN], str)
                                 or not STAND_IN_RE.match(rule[STAND_IN])):
            problems.append(f"{here}.{STAND_IN}: must be the path of a Make file")
        if "section" in rule and not top:
            problems.append(f"{here}: a section only at the top level")
        if "section" in rule and set(rule) - {"section", "comment"}:
            problems.append(f"{here}: a section rule has only `section` and `comment`")
        actions = [k for k in rule if k in ACTIONS]
        unknown = [k for k in rule if k not in ACTIONS + ("comment", STAND_IN) + BRANCHES]
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
                    problems += rules_problems(rule[branch], f"{here}.{branch}", top=False)
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
    if document.get("schema") not in SCHEMAS:
        problems.append(f"schema: must be one of {', '.join(map(str, SCHEMAS))}")
    if "rules" not in document:
        problems.append("document: missing key 'rules'")
    else:
        problems += rules_problems(document["rules"])
        if not problems and document["schema"] < needed_schema(document["rules"]):
            problems.append(f"schema: the rules need schema {needed_schema(document['rules'])}")
    return problems
