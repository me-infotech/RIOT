# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Variables of the configuration data and the word functions on them.

The rules of the data format (dist/tools/config_data/README.md) assign
variables in three flavors: `recursive` (the value keeps its references
and is expanded when it is used), `simple` (expanded once, when assigned)
and `conditional` (recursive, only if the variable is not defined yet).
`add` appends to a variable and keeps its flavor; it creates a recursive
variable. The generated Make adapters use `=`, `:=`, `?=` and `+=` for
them, so the order of evaluation is the same in Make and here.

A recursive value is a list of terms: a text with `${NAME}` references or
a `{select: …}` (schema 2); schema 3 (step G3-1) adds `{files: …}`,
`{subdirs: …}` and `{arith: …}`. Nothing here knows Make syntax.

`files` and `subdirs` look at the file system relative to the directory
named by the variable CURDIR (the directory of the module, as Make's
`$(wildcard …)` in the sub-make of that directory). They only test whether
names exist; they never open a file.
"""

from __future__ import annotations

import glob
import os
import re

REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Where a value comes from: a command line variable (BOARD=… of the CLI)
# wins over every assignment of the data, as on Make's command line.
FILE, COMMAND_LINE = "file", "command line"


def matches(pattern: str, word: str) -> bool:
    """A pattern word with at most one `%` (any text, also empty)."""
    if "%" not in pattern:
        return pattern == word
    prefix, suffix = pattern.split("%", 1)
    return (len(word) >= len(prefix) + len(suffix) and word.startswith(prefix)
            and word.endswith(suffix))


def keep(patterns: list, words: list) -> list:
    """The words that match one of the patterns, in order, with repetitions."""
    return [w for w in words if any(matches(p, w) for p in patterns)]


def drop(patterns: list, words: list) -> list:
    """The words that match none of the patterns, in order, with repetitions."""
    return [w for w in words if not any(matches(p, w) for p in patterns)]


def patsubst(pattern: str, replacement: str, word: str) -> str:
    """Make's pattern substitution of one word (a word that does not match
    stays as it is)."""
    prefix, suffix = pattern.split("%", 1)
    if not matches(pattern, word):
        return word
    stem = word[len(prefix):len(word) - len(suffix)]
    return replacement.replace("%", stem, 1) if "%" in replacement else replacement


def macro_name(word: str) -> str:
    """RIOT's `uppercase_and_underscore` (makefiles/utils/strings.mk)."""
    return word.replace("-", "_").upper() if word.isascii() else word


def unique(words: list) -> list:
    """Without duplicates, first occurrence kept (the `uniq` of Makefile.include)."""
    seen, out = set(), []
    for word in words:
        if word not in seen:
            seen.add(word)
            out.append(word)
    return out


ARITH_TOKEN_RE = re.compile(r"\s*(0[xX][0-9a-fA-F]+|[0-9]+K?|[-+*()])")


def arith(expr: str) -> int:
    """Value of an expression of integers (decimal, 0x hexadecimal, `NK` =
    N*1024), `+`, `-`, `*` and parentheses, as the shell's `$((…))` of
    RIOT's Make files computes it."""
    tokens, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        match = ARITH_TOKEN_RE.match(expr, pos)
        if not match:
            raise ValueError(f"not an arithmetic expression: {expr!r}")
        tokens.append(match.group(1))
        pos = match.end()
        while pos < len(expr) and expr[pos].isspace():
            pos += 1

    def number(tok):
        if tok.endswith("K"):
            return int(tok[:-1], 0) * 1024
        return int(tok, 16) if tok.lower().startswith("0x") else int(tok, 10)

    def parse_sum(i):
        value, i = parse_product(i)
        while i < len(tokens) and tokens[i] in "+-":
            rhs, j = parse_product(i + 1)
            value = value + rhs if tokens[i] == "+" else value - rhs
            i = j
        return value, i

    def parse_product(i):
        value, i = parse_atom(i)
        while i < len(tokens) and tokens[i] == "*":
            rhs, i = parse_atom(i + 1)
            value *= rhs
        return value, i

    def parse_atom(i):
        if i >= len(tokens):
            raise ValueError(f"incomplete expression: {expr!r}")
        if tokens[i] == "(":
            value, i = parse_sum(i + 1)
            if i >= len(tokens) or tokens[i] != ")":
                raise ValueError(f"unbalanced parentheses: {expr!r}")
            return value, i + 1
        if tokens[i] == "-":
            value, i = parse_atom(i + 1)
            return -value, i
        return number(tokens[i]), i + 1

    value, end = parse_sum(0)
    if end != len(tokens):
        raise ValueError(f"not an arithmetic expression: {expr!r}")
    return value


def sort(words) -> list:
    """Sorted, without duplicates (byte order; all words here are ASCII)."""
    return sorted(set(words))


class Variables:
    """name -> (flavor, value, origin); value: str (simple) or list of terms."""

    def __init__(self):
        self._vars: dict = {}

    # -- reading ---------------------------------------------------------------
    def defined(self, name: str) -> bool:
        return name in self._vars

    def flavor(self, name: str):
        return self._vars[name][0] if name in self._vars else None

    def origin(self, name: str):
        return self._vars[name][2] if name in self._vars else None

    def get(self, name: str) -> str:
        """The expanded value ('' if undefined)."""
        if name not in self._vars:
            return ""
        flavor, value, _ = self._vars[name]
        if flavor == "simple":
            return value
        return " ".join(t for t in (self.term(x) for x in value) if t)

    def words(self, name: str) -> list:
        return self.get(name).split()

    def names(self) -> list:
        return sorted(self._vars)

    # -- expansion -------------------------------------------------------------
    def text(self, text: str) -> str:
        """`${NAME}` replaced by the value of NAME."""
        return REF_RE.sub(lambda m: self.get(m.group(1)), text)

    def patterns(self, words) -> list:
        """Pattern words; a whole word `${NAME}` stands for the words of NAME."""
        out = []
        for word in words or []:
            ref = REF_RE.fullmatch(word)
            out += self.words(ref.group(1)) if ref else [word]
        return out

    def select(self, sel: dict) -> list:
        """The words of a selection {var, match?, except?, replace?}."""
        words = self.words(sel["var"])
        if sel.get("except"):
            words = drop(self.patterns(sel["except"]), words)
        if sel.get("match"):
            words = keep(self.patterns(sel["match"]), words)
        if "replace" in sel:
            old, new = sel["replace"]["from"], sel["replace"]["to"]
            words = [w.replace(old, new) for w in words]
        if sel.get("macro"):
            words = [macro_name(w) for w in words]
        if "pattern" in sel:
            old, new = self.text(sel["pattern"]["from"]), self.text(sel["pattern"]["to"])
            words = [patsubst(old, new, w) for w in words]
        if sel.get("unique"):
            words = unique(words)
        return [w for w in words if w]

    def _base(self) -> str:
        curdir = self.get("CURDIR")
        if not curdir:
            raise ValueError("`files`/`subdirs` need CURDIR (the directory of the module)")
        return curdir

    def files(self, spec: dict) -> list:
        """Make's `$(wildcard G…)`: the names that exist, each pattern sorted
        (GNU Make >= 4.3), relative names relative to CURDIR."""
        out = []
        for pattern in spec["match"]:
            pattern = self.text(pattern)
            if os.path.isabs(pattern):
                out += sorted(glob.glob(pattern))
            else:
                base = self._base()
                out += sorted(os.path.relpath(p, base)
                              for p in glob.glob(os.path.join(glob.escape(base), pattern)))
        if spec.get("except"):
            out = drop(self.patterns(spec["except"]), out)
        return out

    def subdirs(self, spec: dict) -> list:
        """`$(dir $(wildcard $(addsuffix /FILE,SEL)))`: `word/` for each
        selected word whose directory has FILE."""
        base = self._base()
        return [w + "/" for w in self.select(spec["select"])
                if os.path.exists(os.path.join(base, w, spec["file"]))]

    def term(self, term) -> str:
        if isinstance(term, dict):
            if "files" in term:
                return " ".join(self.files(term["files"]))
            if "subdirs" in term:
                return " ".join(self.subdirs(term["subdirs"]))
            if "arith" in term:
                value = arith(self.text(term["arith"]["expr"]))
                return hex(value) if term["arith"].get("format") == "hex" else str(value)
            return " ".join(self.select(term["select"]))
        return self.text(term)

    # -- assignment ------------------------------------------------------------
    def _locked(self, name: str, origin: str) -> bool:
        return self.origin(name) == COMMAND_LINE and origin != COMMAND_LINE

    def set(self, name: str, value, flavor: str = "recursive", origin: str = FILE):
        """`set` of the data format (value: text or {select: …})."""
        if self._locked(name, origin):
            return
        if flavor == "conditional":
            if name in self._vars:
                return
            flavor = "recursive"
        if flavor == "simple":
            self._vars[name] = ("simple", self.term(value), origin)
        else:
            self._vars[name] = ("recursive", [value], origin)

    def add(self, name: str, item, origin: str = FILE):
        """`add` of one item (text or {select: …}), like `VAR += item`."""
        if self._locked(name, origin):
            return
        if name not in self._vars:
            self._vars[name] = ("recursive", [item], origin)
            return
        flavor, value, old_origin = self._vars[name]
        if flavor == "simple":
            new = self.term(item)
            self._vars[name] = ("simple", f"{value} {new}".strip() if value else new,
                                old_origin)
        else:
            self._vars[name] = ("recursive", value + [item], old_origin)

    def set_words(self, name: str, words, origin: str = FILE):
        """A simple variable with these words (what `V := $(…)` of the build
        system's algorithm does)."""
        if self._locked(name, origin):
            return
        self._vars[name] = ("simple", " ".join(words), origin)

    def command_line(self, name: str, value: str):
        self._vars[name] = ("recursive", [value], COMMAND_LINE)

    def snapshot(self) -> dict:
        """Every variable, expanded (for the JSON state)."""
        return {name: self.get(name) for name in self.names()}
