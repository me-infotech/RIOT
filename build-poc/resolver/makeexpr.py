# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Evaluator for the small subset of GNU Make expressions that occurs in
RIOT's dependency files (fallback for conditions/values that are not
expressed as structured data).

Supported: $(VAR), ${VAR}, $(VAR:a%b=c%d) and $(VAR:.a=.b) substitution
references, and the functions filter, filter-out, findstring, sort, words,
word, firstword, lastword, subst, patsubst, strip, if, or, and, call
(only for user functions given as variables, $1..$9).
Anything else raises UnsupportedExpr.
"""

import glob
import os
import re

# Context for functions that touch the outside world. CWD: directory for
# relative paths ($(wildcard), $(abspath)); SHELL: callable(cmd) -> output
# for $(shell …) (the resolver maps known commands to named Python blocks
# and refuses unknown ones); MESSAGES: list collecting $(info/warning).
CWD = "."
SHELL = None
MESSAGES: list = []
CHECK_ONLY = False
# automatic variables while a recipe is expanded ("@", "<", "^", "*")
AUTOMATIC: dict = {}
# EVAL: callable(text) that parses and runs text as make file content
EVAL = None

FUNCS = {"filter", "filter-out", "findstring", "sort", "words", "word",
         "firstword", "lastword", "subst", "patsubst", "strip", "if", "or",
         "and", "call", "foreach", "wordlist", "wildcard", "addprefix",
         "addsuffix", "abspath", "realpath", "dir", "notdir", "basename",
         "suffix", "join", "origin", "flavor", "value", "info", "warning",
         "error", "shell", "eval", "file"}


class UnsupportedExpr(Exception):
    pass


def _split_args(s: str) -> list[str]:
    """Split at top-level commas."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "({":
            depth += 1
        elif ch in ")}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _pattern_match(pat: str, word: str) -> bool:
    if "%" not in pat:
        return pat == word
    pre, post = pat.split("%", 1)
    return len(word) >= len(pre) + len(post) and word.startswith(pre) and \
        word.endswith(post)


def _patsubst(pat: str, rep: str, word: str) -> str:
    if "%" not in pat:
        return rep if word == pat else word
    pre, post = pat.split("%", 1)
    if not _pattern_match(pat, word):
        return word
    stem = word[len(pre):len(word) - len(post) if post else None]
    return rep.replace("%", stem, 1) if "%" in rep else rep


def evaluate(expr: str, lookup, args: list[str] | None = None) -> str:
    """Expand expr; lookup(name) -> value string (unexpanded)."""
    out, i = "", 0
    while i < len(expr):
        ch = expr[i]
        if ch == "$" and i + 1 < len(expr):
            nxt = expr[i + 1]
            if nxt == "$":
                out += "$"
                i += 2
                continue
            if nxt in "({":
                close = ")" if nxt == "(" else "}"
                depth, j = 0, i + 1
                while j < len(expr):
                    if expr[j] in "({":
                        depth += 1
                    elif expr[j] in ")}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                if j >= len(expr) or expr[j] != close:
                    raise UnsupportedExpr(f"unbalanced: {expr}")
                out += _ref(expr[i + 2:j], lookup, args)
                i = j + 1
                continue
            if nxt.isdigit() and args is not None:
                k = int(nxt)
                out += args[k - 1] if k <= len(args) else ""
                i += 2
                continue
            if nxt.isalpha() or nxt == "_":
                # single-character variable, e.g. $_ in $(foreach _,…)
                value = lookup(nxt)
                out += evaluate(value, lookup, args) if value else ""
                i += 2
                continue
            if nxt in AUTOMATIC:
                out += AUTOMATIC[nxt]
                i += 2
                continue
            if nxt in "@<^*?%+|":
                if CHECK_ONLY:
                    i += 2
                    continue
                raise UnsupportedExpr(f"automatic variable ${nxt} outside a recipe")
        out += ch
        i += 1
    return out


def _ref(body: str, lookup, args) -> str:
    m = re.match(r"^([\w.-]+)\s+(.*)$", body, re.S)
    if m and m.group(1) in FUNCS:
        fn, rest = m.group(1), m.group(2)
        raw = _split_args(rest)
        ev = lambda s: evaluate(s, lookup, args)  # noqa: E731
        if fn == "if":
            cond = ev(raw[0]).strip()
            return ev(raw[1]) if cond else (ev(",".join(raw[2:])) if len(raw) > 2 else "")
        if fn == "or":
            for a in raw:
                v = ev(a).strip()
                if v:
                    return v
            return ""
        if fn == "and":
            v = ""
            for a in raw:
                v = ev(a).strip()
                if not v:
                    return ""
            return v
        if fn == "foreach":
            var = ev(raw[0]).strip()
            items = ev(raw[1]).split()
            body = ",".join(raw[2:])
            res = []
            for item in items:
                def look(name, _item=item, _var=var):
                    return _item if name == _var else lookup(name)
                res.append(evaluate(body, look, args))
            # like Make: results joined by one space, not stripped (a
            # $(NEWLINE) at the end of each result must survive)
            return " ".join(res)
        if fn == "call":
            name = ev(raw[0]).strip()
            value = lookup(name)
            if value is None:
                raise UnsupportedExpr(f"call of unknown function {name}")
            return evaluate(value, lookup, [ev(a) for a in raw[1:]])
        if fn == "file":
            # $(file >name,text) / $(file >>name,text) / $(file <name)
            spec = ev(raw[0]).strip()
            text = ev(",".join(raw[1:])) if len(raw) > 1 else None
            if CHECK_ONLY:
                return ""
            op = ">>" if spec.startswith(">>") else spec[0]
            name = spec[len(op):].strip()
            path = name if os.path.isabs(name) else os.path.join(CWD, name)
            if op == "<":
                return open(path).read().rstrip("\n") if os.path.exists(path) else ""
            with open(path, "a" if op == ">>" else "w") as f:
                if text is not None:
                    f.write(text + "\n")
            return ""
        if fn == "eval":
            text = ev(",".join(raw))
            if CHECK_ONLY:
                return ""
            if EVAL is None:
                raise UnsupportedExpr("$(eval …) without an interpreter")
            EVAL(text)
            return ""
        if fn == "value":
            return lookup(ev(raw[0]).strip()) or ""
        if fn in ("origin", "flavor"):
            return "file" if lookup(ev(raw[0]).strip()) is not None else "undefined"
        vals = [ev(a) for a in raw]
        if fn in ("info", "warning", "error"):
            text = ",".join(vals)
            if not CHECK_ONLY:
                MESSAGES.append((fn, text))
                if fn == "error":
                    raise UnsupportedExpr(f"$(error {text})")
            return ""
        if fn == "shell":
            if CHECK_ONLY:
                return ""
            if SHELL is None:
                raise UnsupportedExpr(f"$(shell {vals[0][:60]})")
            return SHELL(",".join(vals))
        if fn == "wildcard":
            if CHECK_ONLY:
                return ""
            out = []
            for pat in vals[0].split():
                full = pat if os.path.isabs(pat) else os.path.join(CWD, pat)
                hits = sorted(glob.glob(full))
                out += [h if os.path.isabs(pat) else os.path.relpath(h, CWD)
                        for h in hits]
            return " ".join(out)
        if fn == "addprefix":
            return " ".join(vals[0].strip() + w for w in vals[1].split())
        if fn == "addsuffix":
            return " ".join(w + vals[0].strip() for w in vals[1].split())
        if fn in ("abspath", "realpath"):
            res = []
            for w in vals[0].split():
                full = w if os.path.isabs(w) else os.path.join(CWD, w)
                full = os.path.normpath(full) if fn == "abspath" else \
                    os.path.realpath(full)
                if fn == "realpath" and not os.path.exists(full):
                    continue
                res.append(full)
            return " ".join(res)
        if fn == "dir":
            return " ".join((os.path.dirname(w) or ".") + "/" for w in vals[0].split())
        if fn == "notdir":
            return " ".join(os.path.basename(w) for w in vals[0].split())
        if fn == "basename":
            return " ".join(os.path.splitext(w)[0] for w in vals[0].split())
        if fn == "suffix":
            return " ".join(os.path.splitext(w)[1] for w in vals[0].split()
                            if os.path.splitext(w)[1])
        if fn == "join":
            a, b = vals[0].split(), vals[1].split()
            return " ".join((a[k] if k < len(a) else "") + (b[k] if k < len(b) else "")
                            for k in range(max(len(a), len(b))))
        if fn == "filter":
            pats = vals[0].split()
            return " ".join(w for w in vals[1].split()
                            if any(_pattern_match(p, w) for p in pats))
        if fn == "filter-out":
            pats = vals[0].split()
            return " ".join(w for w in vals[1].split()
                            if not any(_pattern_match(p, w) for p in pats))
        if fn == "findstring":
            return vals[0] if vals[0] in vals[1] else ""
        if fn == "sort":
            return " ".join(sorted(set(vals[0].split())))
        if fn == "words":
            return str(len(vals[0].split()))
        if fn == "word":
            ws = vals[1].split()
            k = int(vals[0].strip())
            return ws[k - 1] if 0 < k <= len(ws) else ""
        if fn == "firstword":
            ws = vals[0].split()
            return ws[0] if ws else ""
        if fn == "wordlist":
            ws = vals[2].split()
            a, b = int(vals[0].strip()), int(vals[1].strip())
            return " ".join(ws[a - 1:b])
        if fn == "lastword":
            ws = vals[0].split()
            return ws[-1] if ws else ""
        if fn == "subst":
            return vals[2].replace(vals[0], vals[1])
        if fn == "patsubst":
            return " ".join(_patsubst(vals[0].strip(), vals[1].strip(), w)
                            for w in vals[2].split())
        if fn == "strip":
            return " ".join(vals[0].split())
    if m:
        raise UnsupportedExpr(f"function {m.group(1)}")
    # substitution reference $(VAR:a=b)
    if ":" in body and "=" in body.split(":", 1)[1]:
        var, rule = body.split(":", 1)
        a, b = rule.split("=", 1)
        a, b = evaluate(a, lookup, args), evaluate(b, lookup, args)
        value = evaluate(lookup(var.strip()) or "", lookup, args)
        if "%" not in a:
            a, b = "%" + a, "%" + b
        return " ".join(_patsubst(a, b, w) for w in value.split())
    if body in ("@D", "@F", "<D", "<F", "*D", "*F") and body[0] in AUTOMATIC:
        v = AUTOMATIC[body[0]]
        return (os.path.dirname(v) or ".") if body[1] == "D" else os.path.basename(v)
    if body in AUTOMATIC:
        return AUTOMATIC[body]
    if "$" in body and not re.match(r"^[\w.-]+\s", body):
        # computed variable name, e.g. $(IOTLAB_ARCHI_$(BOARD))
        body = evaluate(body, lookup, args).strip()
    if not re.match(r"^[\w.-]+$", body):
        if CHECK_ONLY:
            return ""
        raise UnsupportedExpr(f"reference {body}")
    value = lookup(body)
    return evaluate(value, lookup, args) if value else ""


def check(expr: str) -> None:
    """Raise UnsupportedExpr if expr uses anything the evaluator lacks.
    Parameters ($1 …) of user functions are allowed."""
    global CHECK_ONLY
    CHECK_ONLY = True
    try:
        evaluate(expr, lambda name: "", [])
    except (ValueError, IndexError):
        pass      # empty values in a dry check (e.g. $(word $1,…)): fine
    finally:
        CHECK_ONLY = False
