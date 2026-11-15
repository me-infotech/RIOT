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


class Value(str):
    """A variable's value as a lookup returns it: the text plus Make's
    flavor ("recursive": expanded when referenced; "simple": already
    expanded, used as is) and origin ("file", "environment", "command
    line", "override", "default", "automatic"). A plain str from a lookup
    counts as a recursive variable from a file."""
    flavor = "recursive"
    origin = "file"


def value(text: str, flavor: str = "recursive", origin: str = "file") -> Value:
    v = Value(text)
    v.flavor, v.origin = flavor, origin
    return v


AUTO_NAMES = set("@<^*?%+|")


def _is_auto(name: str) -> bool:
    """$@ … and the D/F variants ($(@D), $(<F), …)."""
    return name[:1] in AUTO_NAMES and (len(name) == 1 or
                                        (len(name) == 2 and name[1] in "DF"))


def _var(name: str, lookup, args) -> str:
    """Expanded value of the variable name: automatic variables, call
    parameters, simple variables as stored, recursive ones expanded."""
    if _is_auto(name):
        if name[0] not in AUTOMATIC:
            if CHECK_ONLY:
                return ""
            raise UnsupportedExpr(f"automatic variable ${name} outside a recipe")
        v = AUTOMATIC[name[0]]
        if len(name) == 2:
            if name[1] == "D":
                return " ".join(os.path.dirname(w) or "." for w in v.split())
            return " ".join(os.path.basename(w) for w in v.split())
        return v
    if name.isdigit() and args is not None:
        k = int(name)
        return args[k - 1] if 0 < k <= len(args) else ""
    v = lookup(name)
    if not v:
        return ""
    if getattr(v, "flavor", "recursive") == "simple":
        return str(v)
    return evaluate(v, lookup, args)


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
            if nxt.isalnum() or nxt == "_" or nxt in AUTO_NAMES:
                # single-character variable ($_ in $(foreach _,…)), call
                # parameter ($1) or automatic variable ($@)
                out += _var(nxt, lookup, args)
                i += 2
                continue
        out += ch
        i += 1
    return out


def _ref(body: str, lookup, args) -> str:
    if body.isdigit() and args is not None:
        # $(1) / ${1}: parameter of the function being called
        k = int(body)
        return args[k - 1] if 0 < k <= len(args) else ""
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
                def look(name, _item=value(item, "simple", "automatic"),
                         _name=var):
                    return _item if name == _name else lookup(name)
                res.append(evaluate(body, look, args))
            # like Make: results joined by one space, not stripped (a
            # $(NEWLINE) at the end of each result must survive)
            return " ".join(res)
        if fn == "call":
            name = ev(raw[0]).strip()
            fvalue = lookup(name)
            if fvalue is None:
                raise UnsupportedExpr(f"call of unknown function {name}")
            params = [ev(a) for a in raw[1:]]
            if getattr(fvalue, "flavor", "recursive") == "simple":
                return str(fvalue)         # like $(name): not expanded again
            return evaluate(fvalue, lookup, params)
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
            return str(lookup(ev(raw[0]).strip()) or "")
        if fn in ("origin", "flavor"):
            name = ev(raw[0]).strip()
            if (_is_auto(name) and name[0] in AUTOMATIC) or \
                    (args is not None and name.isdigit() and
                     0 < int(name) <= len(args)):
                return "automatic" if fn == "origin" else "simple"
            v = lookup(name)
            if v is None:
                return "undefined"
            return getattr(v, fn, "recursive" if fn == "flavor" else "file")
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
                # relative patterns are matched in CWD and returned in the
                # pattern's own form (`./x` stays `./x`), sorted per pattern
                out += sorted(glob.glob(pat, root_dir=None if os.path.isabs(pat)
                                        else CWD))
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
        # dir/notdir/basename/suffix as in Make's function.c: split at the
        # last `/` and at the last `.` after it ($(dir /) is `/`,
        # $(basename .bashrc) is empty, $(suffix .bashrc) is `.bashrc`)
        if fn == "dir":
            return " ".join(w[:w.rfind("/") + 1] or "./" for w in vals[0].split())
        if fn == "notdir":
            return " ".join(w[w.rfind("/") + 1:] for w in vals[0].split())
        if fn == "basename":
            return " ".join(w[:w.rfind(".")] if w.rfind(".") > w.rfind("/") else w
                            for w in vals[0].split())
        if fn == "suffix":
            return " ".join(w[w.rfind("."):] for w in vals[0].split()
                            if w.rfind(".") > w.rfind("/"))
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
    if "$" in body:
        # like Make: references inside the name are expanded first, e.g.
        # $(IOTLAB_ARCHI_$(BOARD)) or $(L$(X):.c=.o)
        body = evaluate(body, lookup, args)
    colon = body.find(":")
    if colon >= 0 and "=" in body[colon + 1:]:
        # substitution reference $(VAR:a=b), also $(@:ALL--%=%)
        var = body[:colon].strip()
        a, b = body[colon + 1:].split("=", 1)
        text = _var(var, lookup, args)
        if "%" not in a:
            a, b = "%" + a, "%" + b
        return " ".join(_patsubst(a, b, w) for w in text.split())
    body = body.strip()
    if _is_auto(body):
        return _var(body, lookup, args)
    if not re.match(r"^[\w.-]+$", body):
        if CHECK_ONLY:
            return ""
        raise UnsupportedExpr(f"reference {body}")
    return _var(body, lookup, args)


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
