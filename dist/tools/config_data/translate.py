# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Translator: a RIOT dependency or feature file in Make syntax -> rule list.

Used once per file to convert it (later scopes use it again). It accepts
only the statements the data format can express without Make syntax and
stops with the file and line of anything else (`Unsupported`); there is no
fallback that keeps a Make expression.

Accepted statements (blanks around tokens do not matter):

  ifneq/ifeq (,$(filter P…,$(V)))                 has / not has
  ifneq/ifeq (,$(filter P…,$(filter-out E…,$(V)))) has … except
  ifneq/ifeq (,$(filter-out E…,$(filter P…,$(V)))) has … except (same meaning)
  ifeq/ifneq (w…,$(filter P…,$(V)))               selection_equals / not
  ifneq/ifeq (,$(filter $(V),w…))                 one_of / not
  ifeq/ifneq ($(V),w) ($(V1) $(V2),w1 w2) (,$(V)) equals / not
  (the two arguments may be given in either order)
  else, else ifeq/ifneq … (kept as `elif`), endif
  V += words   V = text   V := text   V ?= text
  include/-include path…   path: text, $(V:%=…%…) or $(sort $(V:%=…%…))
  $(error|warning|info text)
  full-line and trailing comments (kept as `comment`)

Text may refer to variables as $(V) or ${V}; it is stored as ${V}.
"""

import re

from rules import NAME

COND_RE = re.compile(r"^(ifeq|ifneq)\s*(.*)$")
ASSIGN_RE = re.compile(rf"^({NAME})\s*(\+=|:=|\?=|=)\s*(.*)$")
INCLUDE_RE = re.compile(r"^(-include|sinclude|include)\s+(.*)$")
REF_ONLY_RE = re.compile(rf"^\$[({{]({NAME})[)}}]$")
MAKE_REF_RE = re.compile(rf"\$[({{]({NAME})[)}}]")
SUBST_RE = re.compile(rf"^\$\(({NAME}):%=(.*)\)$")
FLAVOR = {"=": None, ":=": "simple", "?=": "conditional"}


class Unsupported(ValueError):
    """A statement the data format cannot express (yet)."""


def _close(text: str, start: int) -> int:
    """Index of the `)` matching the `(` at text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise Unsupported(f"unbalanced parentheses in {text!r}")


def _split_top(text: str, sep: str) -> list:
    """Split at `sep` outside parentheses (sep "" means blanks)."""
    parts, depth, cur = [], 0, []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and ((sep and char == sep) or (not sep and char.isspace())):
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(char)
    parts.append("".join(cur))
    return parts if sep else [p for p in parts if p]


def _call(text: str):
    """(function, [arguments]) if text is exactly one `$(function args)`."""
    if not text.startswith("$(") or _close(text, 1) != len(text) - 1:
        return None
    inner = text[2:-1]
    match = re.match(r"^([a-z-]+)\s+(.*)$", inner, re.S)
    if not match:
        return None
    return match.group(1), [a.strip() for a in _split_top(match.group(2), ",")]


def template(text: str) -> str:
    """Make text with plain variable references -> `${NAME}` text."""
    result = MAKE_REF_RE.sub(r"${\1}", text)
    if "$" in MAKE_REF_RE.sub("", text):
        raise Unsupported(f"Make function or computed reference in {text!r}")
    return result


def _patterns(text: str) -> list:
    words = text.split()
    if not words or any("$" in w or "(" in w for w in words):
        raise Unsupported(f"pattern list {text!r}")
    return words


def _operand(text: str):
    """Classify one argument of ifeq/ifneq."""
    text = text.strip()
    if text == "":
        return ("empty",)
    if "$" not in text and "(" not in text and ")" not in text:
        return ("words", text.split())
    refs = text.split()
    if all(REF_ONLY_RE.match(r) for r in refs):
        return ("refs", [REF_ONLY_RE.match(r).group(1) for r in refs])
    call = _call(text)
    if call and len(call[1]) == 2:
        func, (first, second) = call
        ref = REF_ONLY_RE.match(first)
        if func == "filter" and ref and "$" not in second:
            return ("one_of", {"var": ref.group(1), "values": _patterns(second)})
        inner = REF_ONLY_RE.match(second)
        if func == "filter" and inner:
            return ("select", {"var": inner.group(1), "match": _patterns(first)})
        nested = _call(second)
        if (nested and len(nested[1]) == 2 and REF_ONLY_RE.match(nested[1][1])
                and {func, nested[0]} == {"filter", "filter-out"}):
            # filter and filter-out keep or drop each word on its own, so
            # their order does not change the result
            var = REF_ONLY_RE.match(nested[1][1]).group(1)
            match, excl = (first, nested[1][0]) if func == "filter" else (nested[1][0], first)
            return ("select", {"var": var, "match": _patterns(match),
                               "except": _patterns(excl)})
    raise Unsupported(f"condition operand {text!r}")


def condition(kind: str, args: str) -> dict:
    """The condition of `ifeq|ifneq args`."""
    args = args.strip()
    if not (args.startswith("(") and _close(args, 0) == len(args) - 1):
        raise Unsupported(f"{kind} {args}: only the form ({{a}},{{b}}) is supported")
    parts = _split_top(args[1:-1], ",")
    if len(parts) != 2:
        raise Unsupported(f"{kind} {args}: two arguments expected")
    ops = [_operand(p) for p in parts]
    kinds = sorted(o[0] for o in ops)
    by_kind = {o[0]: o for o in ops}
    positive = kind == "ifneq"  # true when the operands differ
    if kinds == ["empty", "select"]:
        cond = {"has": by_kind["select"][1]}
    elif kinds == ["empty", "one_of"]:
        cond = {"one_of": by_kind["one_of"][1]}
    elif kinds == ["select", "words"]:
        cond = {"selection_equals": {**by_kind["select"][1], "words": by_kind["words"][1]}}
        positive = not positive
    elif kinds in (["empty", "refs"], ["refs", "words"]):
        names = by_kind["refs"][1]
        values = by_kind["words"][1] if "words" in by_kind else [""]
        if len(names) != len(values):
            raise Unsupported(f"{kind} {args}: number of variables and values differ")
        cond = {"equals": dict(zip(names, values))}
        positive = not positive
    else:
        raise Unsupported(f"{kind} {args}")
    return cond if positive else {"not": cond}


def _comment_split(line: str):
    """(code, trailing comment or None): `#` outside $(…) starts a comment."""
    depth = 0
    for i, char in enumerate(line):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "#" and depth == 0 and (i == 0 or line[i - 1] != "\\"):
            return line[:i].rstrip(), _comment_text(line[i + 1:])
    return line.rstrip(), None


def _comment_text(text: str) -> str:
    text = text.rstrip()
    return text[1:] if text.startswith(" ") else text


def _lines(text: str):
    """(line number, kind, code, comment); kind: blank, comment, code."""
    physical = text.split("\n")
    i = 0
    while i < len(physical):
        number, raw = i + 1, physical[i]
        i += 1
        while (len(raw) - len(raw.rstrip("\\"))) % 2 == 1 and i < len(physical):
            raw = raw[:-1].rstrip() + " " + physical[i].lstrip()
            i += 1
        stripped = raw.strip()
        if not stripped:
            yield number, "blank", "", None
        elif stripped.startswith("#"):
            yield number, "comment", "", _comment_text(stripped[1:])
        else:
            code, comment = _comment_split(stripped)
            yield number, "code", code, comment


def _include(code: str) -> list:
    keyword, rest = INCLUDE_RE.match(code).groups()
    optional = keyword != "include"
    out = []
    for word in _split_top(rest.strip(), ""):
        inc = {}
        call = _call(word)
        if call and call[0] == "sort" and len(call[1]) == 1:
            inc["sort"] = True
            word = call[1][0].strip()
        subst = SUBST_RE.match(word)
        if subst:
            inc = {"for_each": subst.group(1), "path": template(subst.group(2)), **inc}
            if inc["path"].count("%") != 1:
                raise Unsupported(f"include {word!r}: one `%` expected")
        elif "sort" in inc:
            raise Unsupported(f"include $(sort …) without $(V:%=…) in {code!r}")
        else:
            inc["path"] = template(word)
        if optional:
            inc["optional"] = True
        out.append({"include": {k: inc[k] for k in ("for_each", "path", "sort", "optional")
                                if k in inc}})
    return out


def _statement(code: str) -> list:
    """Rules of one statement that is not a conditional."""
    if INCLUDE_RE.match(code):
        return _include(code)
    call = _call(code) if code.startswith("$(") else None
    if call and call[0] in ("error", "warning", "info"):
        return [{call[0]: template(code[len(call[0]) + 3:-1].lstrip())}]
    match = ASSIGN_RE.match(code)
    if match:
        var, op, value = match.groups()
        value = template(value.strip())
        if op == "+=":
            items = [value] if '"' in value else value.split()
            if not items:
                raise Unsupported(f"{code!r}: += without words")
            return [{"add": {var: items}}]
        rule = {"var": var, "value": value}
        if FLAVOR[op]:
            rule["flavor"] = FLAVOR[op]
        return [{"set": rule}]
    raise Unsupported(f"statement {code!r}")


def translate(text: str, path: str = "<text>") -> list:
    """The rule list of a Make file; raises Unsupported with file:line."""
    root = []
    stack = [{"body": root}]
    pending = []          # comment lines waiting for the next statement
    mergeable = [False]   # the last rule of the body may take more words

    def flush():
        if pending:
            stack[-1]["body"].append({"comment": "\n".join(pending)})
            pending.clear()
        mergeable[0] = False

    def emit(rule, trailing):
        lines = pending + ([trailing] if trailing is not None else [])
        pending.clear()
        body = stack[-1]["body"]
        # `V += a` `V += b` on adjacent lines become one rule; a comment
        # stays with the line it was written for
        if (not lines and mergeable[0] and "add" in rule and body and "add" in body[-1]
                and "comment" not in body[-1] and set(body[-1]["add"]) == set(rule["add"])):
            (var, items), = rule["add"].items()
            body[-1]["add"][var] += items
            return body[-1]
        if lines:
            rule = {"comment": "\n".join(lines), **rule}
        body.append(rule)
        mergeable[0] = "add" in rule
        return rule

    for number, kind, code, comment in _lines(text):
        try:
            if kind == "blank":
                flush()
                continue
            if kind == "comment":
                pending.append(comment)
                mergeable[0] = False
                continue
            match = COND_RE.match(code)
            if match:
                rule = emit({"if": condition(match.group(1), match.group(2)), "then": []},
                            comment)
                stack.append({"rule": rule, "body": rule["then"], "line": number})
                mergeable[0] = False
                continue
            if code.split()[0] in ("ifdef", "ifndef"):
                raise Unsupported(f"{code!r}: ifdef/ifndef are not part of the format yet")
            if code == "else" or code.startswith("else "):
                flush()
                if len(stack) < 2 or "else" in stack[-1]["rule"]:
                    raise Unsupported("else without if")
                frame = stack[-1]
                rest = code[4:].strip()
                if rest:
                    # `else ifeq …`: one more branch of the same if, closed
                    # by the same endif
                    match = COND_RE.match(rest)
                    if not match:
                        raise Unsupported(f"else {rest!r}")
                    branch = {"if": condition(match.group(1), match.group(2)), "then": []}
                    if comment is not None:
                        branch = {"comment": comment, **branch}
                    frame["rule"].setdefault("elif", []).append(branch)
                    frame["body"] = branch["then"]
                else:
                    frame["rule"]["else"] = []
                    frame["body"] = frame["rule"]["else"]
                    if comment is not None:
                        pending.append(comment)
                mergeable[0] = False
                continue
            if code == "endif":
                flush()
                if len(stack) < 2:
                    raise Unsupported("endif without if")
                stack.pop()
                if comment is not None:
                    pending.append(comment)
                continue
            if code.split()[0] in ("define", "export", "unexport", "override",
                                   "undefine", "vpath", "private"):
                raise Unsupported(f"{code!r}: not part of the format")
            for rule in _statement(code):
                emit(rule, comment)
                comment = None
        except Unsupported as err:
            raise Unsupported(f"{path}:{number}: {err}") from None
    if len(stack) > 1:
        raise Unsupported(f"{path}:{stack[-1]['line']}: missing endif")
    flush()
    return root
