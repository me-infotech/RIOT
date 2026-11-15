#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Translate RIOT's dependency make files (Makefile.dep, Makefile.features)
into data: an ordered list of rules per file (JSON), for the Python resolver
(roadmap P6, decision D25).

Supported constructs (anything else is recorded as "unsupported" with file
and line, and counted):

  ifneq (,$(filter P1 P2%,$(VAR)))      -> {"any": [VAR, [P1, P2%]]}
  ifeq (,$(filter …,$(VAR)))            -> {"none": [VAR, […]]}
  ifneq (,$(filter-out …,$(VAR)))       -> {"any_out": [VAR, […]]}
  ifeq (,$(filter-out …,$(VAR)))        -> {"none_out": [VAR, […]]}
  ifeq ($(VAR),value) / ifneq           -> {"eq"/"ne": [VAR, value]}
  ifeq (value,$(VAR)) / ifneq           -> same
  ifdef VAR / ifndef VAR                -> {"def"/"undef": VAR}
  else, else if…, endif, nesting
  VAR += words / VAR := words / VAR ?= words / VAR = words
        (words may contain plain $(VAR) references)
  include / -include <path with $(VAR) and %-free words>
  $(error|warning|info …), $(call echowarn|echoinfo|echoerror,…)
                                        -> {"message": level, "text": …}

Fallback (counted separately as "expr"): conditions, values and include
paths with other Make functions are kept as expression strings if the
evaluator in makeexpr.py supports every function they use.

Usage: translate_deps.py <riot root> <output.json>
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from makeexpr import UnsupportedExpr, _split_args, check  # noqa: E402

COND_RE = re.compile(r"^(ifeq|ifneq)\s*(.*)$")
FILTER_RE = re.compile(
    r"^\(\s*,\s*\$\((filter|filter-out)\s+([^,]+?),\s*\$\((\w+)\)\s*\)\s*\)$")
FILTER_RE2 = re.compile(
    r"^\(\s*\$\((filter|filter-out)\s+([^,]+?),\s*\$\((\w+)\)\s*\)\s*,\s*\)$")
EQ_RE = re.compile(r"^\(\s*\$\((\w+)\)\s*,\s*([^$(),]*)\s*\)$")
EQ_RE2 = re.compile(r"^\(\s*([^$(),]*)\s*,\s*\$\((\w+)\)\s*\)$")
ASSIGN_RE = re.compile(r"^([\w.-]+)\s*(\+=|:=|\?=|=)\s*(.*)$")
INCLUDE_RE = re.compile(r"^(-?include)\s+(.+)$")
MSG_RE = re.compile(r"^\$\((?:(error|warning|info)\s|call\s+(echowarn|echoinfo|"
                    r"echoerror)\s*,)(.*)\)$")
SIMPLE_WORD = re.compile(r"^(?:[^$()\s]|\$\(\w+\))+$")


class Unsupported(Exception):
    pass


def parse_cond(kind: str, arg: str) -> dict:
    arg = arg.strip()
    m = FILTER_RE.match(arg) or FILTER_RE2.match(arg)
    if m:
        fn, pats, var = m.groups()
        pats = pats.split()
        if any("$" in p for p in pats):
            pats = None                     # falls through to the fallback
    if m and pats is not None:
        if fn == "filter":
            return {("any" if kind == "ifneq" else "none"): [var, pats]}
        return {("any_out" if kind == "ifneq" else "none_out"): [var, pats]}
    m = EQ_RE.match(arg)
    if m:
        var, val = m.group(1), m.group(2).strip()
        return {("ne" if kind == "ifneq" else "eq"): [var, val]}
    m = EQ_RE2.match(arg)
    if m:
        val, var = m.group(1).strip(), m.group(2)
        return {("ne" if kind == "ifneq" else "eq"): [var, val]}
    # fallback: ifeq/ifneq (a,b) with supported functions
    if arg.startswith("(") and arg.endswith(")"):
        parts = _split_args(arg[1:-1])
        if len(parts) == 2:
            try:
                check(parts[0])
                check(parts[1])
            except UnsupportedExpr as e:
                raise Unsupported(f"condition {kind} {arg} ({e})")
            return {"expr": [kind, parts[0].strip(), parts[1].strip()]}
    raise Unsupported(f"condition {kind} {arg}")


DEFINE_RE = re.compile(
    r"^(?:override\s+|export\s+)?define\s+([\w.-]+)\s*(=|:=|\+=|\?=)?\s*$")
PREFIX_RE = re.compile(r"^(export|unexport|override|undefine)\s+(.*)$")
RULE_RE = re.compile(r"^[^=]*?[^:=\s]\s*:{1,2}(?![=])")


def is_rule(s: str) -> bool:
    """A rule line: a ':' outside of $(…) that is not part of ':=' (and
    the line is no assignment)."""
    if ASSIGN_RE.match(s):
        return False
    depth = 0
    for k, ch in enumerate(s):
        if ch in "({":
            depth += 1
        elif ch in ")}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return not s[k + 1:k + 2] == "="
        elif ch == "=" and depth == 0:
            return False
    return False


def logical_lines(text: str):
    """(line number, text, starts with tab, define body or None): comments
    removed (`\\#` is escaped), continuation lines joined, `define … endef`
    blocks returned whole."""
    lines = text.splitlines()
    buf, start, i = "", 0, 0
    while i < len(lines):
        raw = lines[i]
        n = i + 1
        i += 1
        if not buf:
            start = n
            if raw.lstrip().startswith("#") and not raw.startswith("\t"):
                # full-line comment: kept for the YAML format (D27)
                yield n, raw.strip(), False, None
                continue
            m = DEFINE_RE.match(raw.strip())
            if m and not raw.startswith("\t"):
                body = []
                while i < len(lines) and lines[i].strip() != "endef":
                    body.append(lines[i])
                    i += 1
                i += 1                          # skip endef
                yield n, raw.strip(), False, "\n".join(body)
                continue
        line = raw
        in_recipe = raw.startswith("\t") or (buf and lines[start - 1].startswith("\t"))
        if not in_recipe:
            m = re.search(r"(?<!\\)#", line)
            if m:
                line = line[:m.start()]
        if line.endswith("\\"):
            if lines[start - 1].startswith("\t"):
                # recipe: Make passes backslash-newline on to the shell
                # (a `#` inside a recipe is a shell comment for one line)
                nxt = lines[i] if i < len(lines) else ""
                buf += line + "\n"
                if nxt.startswith("\t"):
                    lines[i] = nxt[1:]
                continue
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            yield start, buf.rstrip(), lines[start - 1].startswith("\t"), None
        buf = ""


def translate(text: str, path: str, unsupported: list) -> list:
    """Nested rule list of one file."""
    root: list = []
    stack = [{"body": root}]          # frames: {"rule", "body"}

    pending: list = []                  # comment lines before the next item

    def emit(item):
        if pending:
            item["comment"] = "\n".join(pending)
            pending.clear()
        stack[-1]["body"].append(item)

    in_rule = False
    for n, line, tab, define in logical_lines(text):
        s = line.strip()
        if s.startswith("#") and define is None and not tab:
            pending.append(s[1:].strip() if s != "#" else "")
            continue
        if define is not None:
            m = DEFINE_RE.match(s)
            op = m.group(2) or "="
            emit({"assign": m.group(1), "op": op, "expr": define,
                  "define": True, "line": n})
            in_rule = False
            continue
        # a tab-indented line after a rule is a recipe (no effect on
        # variables); conditionals inside recipes are still parsed by Make
        if tab and in_rule and not COND_RE.match(s) and \
                not s.startswith(("else", "endif", "ifdef ", "ifndef ")):
            emit({"recipe": s, "line": n})
            continue
        try:
            m = COND_RE.match(s)
            if m:
                rule = {"if": parse_cond(m.group(1), m.group(2)),
                        "then": [], "else": [], "line": n}
                emit(rule)
                stack.append({"rule": rule, "body": rule["then"]})
                continue
            if s.startswith(("ifdef ", "ifndef ")):
                kind, var = s.split(None, 1)
                rule = {"if": {("def" if kind == "ifdef" else "undef"): var.strip()},
                        "then": [], "else": [], "line": n}
                emit(rule)
                stack.append({"rule": rule, "body": rule["then"]})
                continue
            if s == "else" or s.startswith("else "):
                if len(stack) < 2:
                    raise Unsupported("else without if")
                frame = stack[-1]
                rest = s[4:].strip()
                frame["body"] = frame["rule"]["else"]
                if rest:
                    # `else ifeq …`: a nested rule inside else, closed by the
                    # same endif
                    m = COND_RE.match(rest)
                    if rest.startswith(("ifdef ", "ifndef ")):
                        kind, var = rest.split(None, 1)
                        cond = {("def" if kind == "ifdef" else "undef"): var.strip()}
                    elif m:
                        cond = parse_cond(m.group(1), m.group(2))
                    else:
                        raise Unsupported(f"else {rest}")
                    rule = {"if": cond, "then": [], "else": [], "line": n,
                            "chained": True}
                    frame["body"].append(rule)
                    stack.append({"rule": rule, "body": rule["then"],
                                  "chained": True})
                continue
            if s == "endif":
                while stack[-1].get("chained"):
                    stack.pop()
                if len(stack) < 2:
                    raise Unsupported("endif without if")
                stack.pop()
                continue
            m = PREFIX_RE.match(s)
            if m:
                kind, rest = m.group(1), m.group(2).strip()
                if kind in ("export", "override") and ASSIGN_RE.match(rest):
                    s = rest                  # an ordinary assignment below
                    exported = kind == "export"
                    overridden = kind == "override"
                elif kind in ("export", "unexport"):
                    emit({kind: rest.split(), "line": n})
                    continue
                elif kind == "undefine":
                    emit({"undefine": rest, "line": n})
                    continue
                else:
                    raise Unsupported(f"{kind} {rest[:40]}")
            else:
                exported = False
                overridden = False
            in_rule = False
            m = MSG_RE.match(s)
            if m:
                level = m.group(1) or m.group(2)
                level = {"echowarn": "warning", "echoinfo": "info",
                         "echoerror": "error"}.get(level, level)
                emit({"message": level, "text": m.group(3), "line": n})
                continue
            m = INCLUDE_RE.match(s)
            if m:
                words = m.group(2).replace("${", "$(").replace("}", ")").split()
                optional = m.group(1) == "-include"
                if all(SIMPLE_WORD.match(w) for w in words):
                    emit({"include": words, "optional": optional, "line": n})
                    continue
                try:
                    check(m.group(2))
                except UnsupportedExpr as e:
                    raise Unsupported(f"include with functions ({e})")
                emit({"include_expr": m.group(2), "optional": optional,
                      "line": n})
                continue
            m = ASSIGN_RE.match(s)
            if m:
                var, op, value = m.groups()
                words = value.split()
                if all(SIMPLE_WORD.match(w) for w in words):
                    emit({"assign": var, "op": op, "words": words, "line": n,
                          **({"export": True} if exported else {}),
                          **({"override": True} if overridden else {})})
                    continue
                try:
                    check(value)
                except UnsupportedExpr as e:
                    if op != "=":
                        raise Unsupported(f"{var} {op} with functions ({e})")
                    # a recursive variable is only expanded when used: keep
                    # it, the resolver fails if it is ever expanded
                    emit({"assign": var, "op": op, "expr": value,
                          "unchecked": str(e), "line": n})
                    continue
                emit({"assign": var, "op": op, "expr": value, "line": n,
                      **({"export": True} if exported else {}),
                      **({"override": True} if overridden else {})})
                continue
            if is_rule(s):
                in_rule = True
                emit({"rule": s, "line": n})   # no effect on variables
                continue
            if s.startswith("$("):
                try:
                    check(s)
                except UnsupportedExpr as e:
                    raise Unsupported(f"function call at top level ({e})")
                emit({"call": s, "line": n})
                continue
            if RULE_RE.match(s):
                in_rule = True
                emit({"rule": s, "line": n})        # no effect on variables
                continue
            raise Unsupported("unknown statement")
        except Unsupported as e:
            unsupported.append({"file": path, "line": n, "reason": str(e),
                                "text": s[:160]})
            emit({"unsupported": str(e), "text": s[:160], "line": n})
    if pending:
        stack[-1]["body"].append({"note": "\n".join(pending)})
    if len(stack) != 1:
        unsupported.append({"file": path, "line": 0,
                            "reason": "unbalanced conditionals", "text": ""})
    return root


BUILD_PATTERNS = ["Makefile.include", "*Makefile.include", "makefiles/*.mk",
                  "makefiles/**/*.mk", "Makefile.base", "Makefile.modules"]


def main() -> int:
    root, out = sys.argv[1], sys.argv[2]
    extra = BUILD_PATTERNS if "--build" in sys.argv[3:] else []
    files = subprocess.run(
        ["git", "-C", root, "ls-files", "*Makefile.dep", "*Makefile.features",
         "*.dep", "*Makefile.*.features",
         "Makefile.dep", "Makefile.features", "*Makefile.default",
         # pieces of the resolution pipeline that are plain rules
         "makefiles/defaultmodules_regular.inc.mk",
         "makefiles/defaultmodules_deps.inc.mk",
         "makefiles/defaultmodules_no_recursive_deps.inc.mk",
         "makefiles/features_modules.inc.mk"] + extra,
        stdout=subprocess.PIPE, text=True, check=True).stdout.split()
    files = sorted(set(files))
    unsupported: list = []
    rules = {}
    helpers = []          # files only reached through an include
    todo = list(files)
    known_dirs = {"$(RIOTBASE)/": "", "$(RIOTMAKE)/": "makefiles/",
                  "$(RIOTCPU)/": "cpu/", "$(RIOTBOARD)/": "boards/",
                  "$(RIOTPKG)/": "pkg/"}
    while todo:
        f = todo.pop(0)
        if f in rules:
            continue
        text = open(f"{root}/{f}", errors="replace").read()
        rules[f] = translate(text, f, unsupported)
        # follow literal includes (e.g. makefiles/stdio.inc.mk) so that every
        # file the rules include is translated too
        stack = list(rules[f])
        while stack:
            it = stack.pop()
            stack += it.get("then", []) + it.get("else", [])
            for w in it.get("include", []):
                for k, v in known_dirs.items():
                    w = w.replace(k, v)
                if "$" not in w and os.path.isfile(f"{root}/{w}") \
                        and w not in rules:
                    todo.append(w)
                    helpers.append(w)
    files = sorted(rules)
    json.dump({"schema": "riot-dep-rules/0", "files": rules,
               "unsupported": unsupported}, open(out, "w"), indent=1)
    reasons: dict = {}
    for u in unsupported:
        key = re.sub(r"\s.*", "", u["reason"]) if u["reason"].startswith(
            "condition") else u["reason"]
        reasons[key] = reasons.get(key, 0) + 1
    bad_files = {u["file"] for u in unsupported}
    def count(items, key):
        n = 0
        for it in items:
            if isinstance(it, dict):
                if key(it):
                    n += 1
                for k in ("then", "else"):
                    n += count(it.get(k, []), key)
        return n
    total = sum(count(r, lambda it: "line" in it) for r in rules.values())
    fallback = sum(count(r, lambda it: "expr" in it.get("if", {})
                         or "expr" in it or "include_expr" in it)
                   for r in rules.values())
    print(f"statements: {total}; structured: {total - fallback - len(unsupported)}; "
          f"expression fallback: {fallback}; unsupported: {len(unsupported)}")
    print(f"helper files reached through includes: {len(set(helpers))}")
    print(f"files: {len(files)}; fully translated: "
          f"{len(files) - len(bad_files)}; unsupported constructs: "
          f"{len(unsupported)} in {len(bad_files)} files")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
