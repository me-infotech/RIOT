#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Rule-based, reproducible classification of RIOT make targets.

Every named make target is put into one of five groups:

  1   stateless: no application/board context, no build, no artifact
  2A  needs the resolved make context (BOARD, CPU, USEMODULE, ...)
  2B  reads an existing artifact or runtime resource (ELF, flasher, term)
  2C  manages the artifact lifecycle (deletes or installs artifacts)
  3   starts a build (compiler, linker, build graph, host tool build)

The decision rules are the ones of the target inventory
(riot_all_make_targets.xlsx, sheet "Group & Category Definitions"), written
as code: the script reads GNU Make's database (`make -pRrq`) for a fixed
context, expands the recipe of the target and of all its prerequisites, and
applies the rules in a fixed order (3 > 2C > 2B > 2A > 1). The same
repository state and the same contexts always give the same result.

Commands:
  classify   classify the targets of an inventory file, write a CSV
  compare    compare a classification with the reference groups
  scan       list literal target declarations of the repository
  check-new  report targets declared since a base revision that are not in
             the inventory, classify them by the same rules and exit 1
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

GROUPS = ("1", "2A", "2B", "2C", "3")
RANK = {g: i for i, g in enumerate(GROUPS)}

DEFAULT_BOARD = "nrf52840dk"
# Board for targets that the reference board does not define (e.g. the
# native-only targets all-valgrind, all-asan): they are classified in this
# board's context and the CSV says so.
FALLBACK_BOARD = "native64"
APP_CONTEXT = "examples/basic/hello-world"
# Feature contexts: targets that make only defines when a feature is used.
EXTRA_APP_CONTEXTS = (
    "tests/riotboot",
    "examples/advanced/suit_update",
)

# --- signals ---------------------------------------------------------------
# Variables whose use in a recipe means "a compiler/linker runs" (rule B).
BUILD_VARS = {
    "CC", "CXX", "LINK", "AS", "AR", "LD", "RANLIB", "CARGO", "RUSTC",
    "CMAKE", "NINJA",
}
# Literal commands in an expanded recipe that compile or build (rule B).
# A command position in a recipe: line start or after ; && || | ( then/do,
# followed by make's prefixes (@ + -), $(Q)-like variables, quotes and
# environment assignments.
CMD = (r"(?:^|[;&|(]|\bthen\b|\bdo\b)[\s@+-]*(?:\$[({]\w+[)}])*[\s@]*"
       r"(?:[A-Za-z_]\w*=\S*\s+)*\"?")
CMD_VAR_RE = re.compile(CMD + r"\$[({](" + "|".join(sorted(BUILD_VARS)) +
                        r")[)}]", re.M)
BUILD_RE = re.compile(
    CMD + r"(?:\S*/)?(cmake|cargo\s+build|ninja|gcc|g\+\+|clang|"
    r"[\w.-]*-gcc|[\w.-]*-g\+\+|cc|c\+\+|scan-build|go\s+build)(?=[\s\"]|$)",
    re.M,
)
# Prerequisite names that are part of the build graph (rule B).
BUILD_PREREQS = {"all", "link", "pkg-build", "elffile", "hexfile", "binfile",
                 "flashfile"}
# Artifact and runtime resources (rule R): reading them is group 2B.
ARTIFACT_VARS = {
    "ELFFILE", "HEXFILE", "BINFILE", "FLASHFILE", "DEBUG_ELFFILE",
    "FLASHER", "FFLAGS", "FLASHDEPS", "TERMPROG", "TERMFLAGS", "TERMDEPS",
    "TERMENV", "DEBUGGER", "DEBUGGER_FLAGS", "DEBUGSERVER", "DEBUGCLIENT",
    "RESET", "RESET_FLAGS", "PORT", "PROG_DEV", "OBJDUMP", "SIZE", "NM",
    "READELF", "EMULATOR", "IOTLAB_NODE", "IOTLAB_EXP_ID", "PROGRAMMER",
}
# Resolved make context (rule K): group 2A.
CONTEXT_VARS = {
    "BOARD", "CPU", "CPU_MODEL", "CPU_FAM", "CPU_ARCH", "CPU_CORE",
    "APPLICATION", "USEMODULE", "USEPKG", "DEFAULT_MODULE", "BINDIR",
    "BOARDDIR", "APPDIR", "FEATURES_USED", "FEATURES_PROVIDED",
    "FEATURES_REQUIRED", "FEATURES_OPTIONAL", "TOOLCHAIN", "PKG_DIR",
    "PKG_SOURCE_DIR", "PKG_BUILD_DIR", "PKG_URL", "PKG_VERSION",
    "KCONFIG_OUT_CONFIG", "KCONFIG_GENERATED_DEPENDENCIES",
}
CONTEXT_VAR_RE = re.compile(
    r"^(?:BOARDS?|CPU|FEATURES|USEMODULE|USEPKG|DEFAULT_MODULE|"
    r"DISABLE_MODULE|KCONFIG|PKG|PROGRAMMERS?|TOOLCHAINS?|BOARD|CPU|"
    r"DEPENDENCY)(?:_|$)|^APPLICATION$"
)
# Deleting or installing artifacts (rule L): group 2C.
DELETE_RE = re.compile(
    r"(?:^|[\s;&|(@-])(?:rm\s+-[a-zA-Z]*[rf]|git\s+(?:-C\s+\S+\s+)?clean)"
)
DELETE_VARS = {"RM"}

# Rule B6: prerequisites that are build products.
BUILD_PRODUCT_RE = re.compile(r"(?:^|/)[^/\s]+\.(?:elf|hex|bin|lst|o|a|map|uf2)$")
# Rule B7: repository scripts called by a recipe, and build commands in them.
SCRIPT_RE = re.compile(r"((?:[\w.$(){}/-]*/)?[\w.-]+\.(?:sh|py))\b")
SCRIPT_BUILD_RE = re.compile(
    r"^[ \t]*(?:\"?\$\{?MAKE\}?\"?|make)[ \t][^\n#]*\b(?:all|buildtest)\b"
    r"|^[ \t]*(?:cmake|cargo[ \t]+build)\b", re.M
)
# Variables that differ between boards for reasons unrelated to a target.
IGNORED_VARS = {"MAKEFILE_LIST", ".VARIABLES", "MAKEOVERRIDES", "MAKEFLAGS",
                "-*-command-variables-*-", "CURDIR"}

VAR_RE = re.compile(r"\$[({]([A-Za-z0-9_.-]+)(?:[)}]|\s|,)")
CALL_RE = re.compile(r"\$[({]call\s+([A-Za-z0-9_.-]+)")
MAKE_RE = re.compile(
    r"(?:^|[;&|(]|\bthen|\bdo|\belse)[\s@+-]*(?:\$[({]\w+[)}])*\"?(?:\$[({]MAKE[)}]|make)\"?"
    r"(?![\w.-])([^;&|\n]*)", re.M)


@dataclass
class Rule:
    target: str
    prereqs: list[str]
    recipe: list[str]
    source: str = ""


@dataclass
class Database:
    """Parsed `make -pRrq` output of one context."""

    directory: str
    variables: dict[str, str] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    default_goal: str = ""
    board: str = ""
    key: str = ""


def run_make_db(repo: Path, directory: str, board: str,
                makefile: str = "", goal: str = ":") -> str:
    env = dict(os.environ)
    for var in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "BOARD", "QUIET"):
        env.pop(var, None)
    # APP_VER defaults to the current time (makefiles/suit.inc.mk); fix it
    # so that two runs give identical output.
    env.update(LC_ALL="C", BOARD=board, RIOTBASE=str(repo),
               RIOTMAKE=str(repo / "makefiles"), APP_VER="0")
    cmd = ["make", "--no-print-directory", "-C", str(repo / directory)]
    if makefile:
        cmd += ["-f", str(repo / makefile)]
    cmd += ["-pRrq", goal]
    proc = subprocess.run(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, text=True, errors="replace", check=False,
        timeout=300,
    )
    return proc.stdout


ASSIGN_RE = re.compile(r"^([^\s#:=]+) (?::{0,3}=|\?=|\+=|!=) ?(.*)$")
TARGET_RE = re.compile(r"^([^\s#:=][^:=]*?):{1,2}(?!=)\s*(.*)$")
SOURCE_RE = re.compile(r"recipe to execute \(from '([^']+)', line (\d+)\)")


def parse_db(text: str, directory: str, repo: Path) -> Database:
    db = Database(directory)
    section = ""
    lines = text.splitlines()
    i = 0
    prefix = str(repo) + "/"
    while i < len(lines):
        line = lines[i]
        if line.startswith("# Variables"):
            section = "vars"
        elif line.startswith("# Files"):
            section = "files"
        elif line.startswith(("# Directories", "# Implicit Rules",
                              "# Pattern-specific", "# VPATH",
                              "# finished")):
            section = "other"
        elif section == "vars" and line.startswith("define "):
            name = line[7:].strip()
            body = []
            i += 1
            while i < len(lines) and lines[i] != "endef":
                body.append(lines[i])
                i += 1
            db.variables[name] = "\n".join(body)
        elif section == "vars":
            m = ASSIGN_RE.match(line)
            if m:
                db.variables[m.group(1)] = m.group(2)
        elif section == "files" and line and not line.startswith(("#", "\t")):
            if i > 0 and lines[i - 1] == "# Not a target:":
                i += 1
                continue
            m = TARGET_RE.match(line)
            if m and not ASSIGN_RE.match(m.group(2) or "x"):
                names = m.group(1).split()
                prereqs = [p for p in m.group(2).split() if p != "|"]
                recipe: list[str] = []
                source = ""
                j = i + 1
                while j < len(lines) and lines[j] != "":
                    if lines[j].startswith("\t"):
                        recipe.append(lines[j][1:])
                    else:
                        s = SOURCE_RE.search(lines[j])
                        if s:
                            path = os.path.normpath(s.group(1))
                            source = f"{path.removeprefix(prefix)}:{s.group(2)}"
                    j += 1
                for name in names:
                    name = name.removeprefix(prefix)
                    if name in db.rules:
                        old = db.rules[name]
                        old.prereqs += prereqs
                        old.recipe += recipe
                        old.source = old.source or source
                    else:
                        db.rules[name] = Rule(name, list(prereqs),
                                              list(recipe), source)
                i = j
                continue
        i += 1
    db.default_goal = db.variables.get(".DEFAULT_GOAL", "").strip()
    return db


@dataclass
class Verdict:
    group: str
    rule: str
    evidence: str


class Classifier:
    def __init__(self, repo: Path, board: str):
        self.repo = repo
        self.board = board
        self._dbs: dict[tuple[str, str, str, str], Database] = {}
        self._cache: dict[tuple, Verdict | None] = {}
        self._board_vars: dict[str, set[str]] = {}
        self._active: set[tuple] = set()

    def db(self, directory: str, board: str | None = None,
           makefile: str = "", goal: str = ":") -> Database:
        directory = os.path.normpath(directory)
        board = board or self.board
        key = (directory, board, makefile, goal)
        if key not in self._dbs:
            text = run_make_db(self.repo, directory, board, makefile, goal)
            db = parse_db(text, directory, self.repo)
            db.board = board
            db.key = "|".join(key)
            self._dbs[key] = db
        return self._dbs[key]

    def board_sensitive(self, db: Database) -> set[str]:
        """Variables whose definition differs between the reference board and
        the fallback board in the same directory (rule K2): their value
        depends on the resolved board context."""
        if db.key not in self._board_vars:
            other_board = (FALLBACK_BOARD if db.board != FALLBACK_BOARD
                           else DEFAULT_BOARD)
            directory, _, makefile, goal = db.key.split("|")
            other = self.db(directory, other_board, makefile, goal)
            names = {n for n, v in db.variables.items()
                     if other.variables.get(n) != v}
            names -= IGNORED_VARS
            # values that change from run to run (time stamps, random) are
            # not board-dependent: drop what differs in a second run
            again = parse_db(run_make_db(self.repo, directory, db.board,
                                         makefile, goal), directory, self.repo)
            names = {n for n in names
                     if again.variables.get(n) == db.variables.get(n)}
            self._board_vars[db.key] = names
        return self._board_vars[db.key]

    # -- recipe analysis ---------------------------------------------------
    def expand_vars(self, db: Database, text: str) -> tuple[set[str], str]:
        """Return all variable names reachable from text, and the text with
        every reachable variable value appended (for literal matching)."""
        seen: set[str] = set()
        chunks = [text]
        todo = [text]
        while todo:
            chunk = todo.pop()
            names = set(VAR_RE.findall(chunk + " "))
            names |= set(CALL_RE.findall(chunk))
            for name in sorted(names - seen):
                seen.add(name)
                value = db.variables.get(name)
                if value and len(seen) < 400:
                    chunks.append(value)
                    todo.append(value)
        return seen, "\n".join(chunks)

    def expand_text(self, db: Database, text: str, depth: int = 0) -> str:
        """Plain substitution of $(VAR) by its value (no functions)."""
        if depth > 8 or "$" not in text:
            return text
        def sub(m: re.Match) -> str:
            return db.variables.get(m.group(1), m.group(0))
        new = re.sub(r"\$[({]([A-Za-z0-9_.-]+)[)}]", sub, text)
        new = re.sub(r"\$[({]call\s+([A-Za-z0-9_.-]+)[^\n]*?[)}]",
                     lambda m: db.variables.get(m.group(1), m.group(0)), new)
        return new if new == text else self.expand_text(db, new, depth + 1)

    def scripts(self, db: Database, expanded: str) -> list[Path]:
        """Repository scripts called by a recipe (one level, rule B7)."""
        found = []
        for m in SCRIPT_RE.finditer(expanded):
            raw = m.group(1)
            path = Path(raw) if os.path.isabs(raw) else \
                self.repo / db.directory / raw
            try:
                path = path.resolve()
                path.relative_to(self.repo)
            except (ValueError, OSError):
                continue
            if path.is_file() and path not in found:
                found.append(path)
        return found

    def own_verdict(self, db: Database, rule: Rule) -> Verdict | None:
        text = "\n".join(rule.recipe)
        text = re.sub(r"\$(?:@|\(@\)|\{@\})", rule.target, text)
        names, expanded = self.expand_vars(db, text)
        commands = self.expand_text(db, text)
        m = CMD_VAR_RE.search(text)
        if m:
            return Verdict("3", "B1", f"runs compiler variable {m.group(1)}")
        m = BUILD_RE.search(commands)
        if m:
            return Verdict("3", "B2", f"runs build command '{m.group(1)}'")
        sub = self.sub_make(db, commands)
        if sub and sub.group == "3":
            return sub
        for script in self.scripts(db, commands):
            body = script.read_text(errors="replace")
            if SCRIPT_BUILD_RE.search(body):
                rel = script.relative_to(self.repo)
                return Verdict("3", "B7", f"called script {rel} builds")
        if DELETE_RE.search(expanded) or names & DELETE_VARS:
            return Verdict("2C", "L1", "deletes files (rm -r/-f, git clean)")
        if names & ARTIFACT_VARS:
            return Verdict("2B", "R1", "artifact/runtime variable " +
                           ",".join(sorted(names & ARTIFACT_VARS)))
        if sub:
            return sub
        context = {n for n in names
                   if n in CONTEXT_VARS or CONTEXT_VAR_RE.match(n)}
        if context:
            return Verdict("2A", "K1", "context variable " +
                           ",".join(sorted(context)[:6]))
        sensitive = names & self.board_sensitive(db)
        if sensitive:
            return Verdict("2A", "K2", "board-dependent variable " +
                           ",".join(sorted(sensitive)[:4]))
        return None

    def sub_make(self, db: Database, expanded: str) -> Verdict | None:
        """Recursive make: classify the goals it is called with."""
        best: Verdict | None = None
        for m in MAKE_RE.finditer(expanded):
            line = m.group(1)
            if "Makefile.base" in line or re.search(r"\bMODULE=", line):
                v = Verdict("3", "B5", "sub-make of Makefile.base (module "
                                       "compile)")
            else:
                v = self.sub_make_goals(db, line)
            if v and (best is None or RANK[v.group] > RANK[best.group]):
                best = v
        return best

    def sub_make_goals(self, db: Database, line: str) -> Verdict | None:
        args = self.expand_text(db, line).split()
        goals, directory, flags = [], None, set()
        k = 0
        while k < len(args):
            a = args[k].strip("\"'")
            if a == "-C" and k + 1 < len(args):
                directory = args[k + 1].strip("\"'")
                k += 2
                continue
            if a == "-f" and k + 1 < len(args):
                k += 2
                continue
            if a.startswith("-"):
                flags.add(a)
            elif "=" not in a and "$" not in a and \
                    not a.startswith((">", "2>", "\\")):
                goals.append(a)
            k += 1
        if directory is None:
            # make re-reads the same context (e.g. `help`, `info-*`)
            if goals:
                v = None
                for goal in goals:
                    gv = self.classify_in(db, goal, frozenset())
                    if gv and (v is None or RANK[gv.group] > RANK[v.group]):
                        v = Verdict(gv.group, "S1", f"make {goal}: {gv.rule}")
                return v
            return Verdict("2A", "K3", "re-evaluates the make context")
        if "$" in directory:
            return Verdict("3", "B3", f"sub-make in {directory}") \
                if not goals else None
        sub_dir = os.path.normpath(os.path.join(db.directory, directory))
        try:
            (self.repo / sub_dir).resolve().relative_to(self.repo)
        except ValueError:
            return None
        if not (self.repo / sub_dir / "Makefile").is_file():
            return None
        if not goals:
            return Verdict("3", "B3", f"sub-make in {sub_dir} (default goal)")
        v = None
        for goal in goals:
            gv = self.classify_in(self.db(sub_dir, db.board), goal, frozenset())
            if gv and (v is None or RANK[gv.group] > RANK[v.group]):
                v = Verdict(gv.group, "S1",
                            f"sub-make {sub_dir} {goal}: {gv.rule}")
        return v

    # -- closure -------------------------------------------------------------
    def classify_in(self, db: Database, target: str,
                    visiting: frozenset[str]) -> Verdict | None:
        key = (db.key, target)
        if key in self._cache:
            return self._cache[key]
        rule = db.rules.get(target)
        if rule is None or target in visiting or key in self._active:
            return None
        visiting = visiting | {target}
        self._active.add(key)
        try:
            best = self._classify_rule(db, target, rule, visiting)
        finally:
            self._active.discard(key)
        self._cache[key] = best
        return best

    def _classify_rule(self, db: Database, target: str, rule: Rule,
                       visiting: frozenset[str]) -> Verdict:
        best = Verdict("1", "S0", "no context, artifact, lifecycle or "
                                  "build signal")
        if target in BUILD_PREREQS:
            best = Verdict("3", "B4", f"build-graph target '{target}'")
        elif BUILD_PRODUCT_RE.search(target):
            best = Verdict("3", "B6", f"build product '{target}'")
        own = self.own_verdict(db, rule)
        if own and RANK[own.group] > RANK[best.group]:
            best = own
        for pre in rule.prereqs:
            if pre in BUILD_PREREQS:
                v = Verdict("3", "B4", f"prerequisite '{pre}'")
            elif BUILD_PRODUCT_RE.search(pre):
                v = Verdict("3", "B6", f"build product prerequisite "
                                       f"'{os.path.basename(pre)}'")
            else:
                pv = self.classify_in(db, pre, visiting)
                v = pv and Verdict(pv.group, pv.rule,
                                   f"prerequisite '{pre}': {pv.evidence}")
            if v and RANK[v.group] > RANK[best.group]:
                best = v
            if best.group == "3":
                break
        return best

    def contexts_for(self, scope: str, evidence: str) -> list[tuple[str, str]]:
        """(directory, makefile) pairs to try, most specific first."""
        path = re.split(r"[:\s;]", evidence.strip(), maxsplit=1)[0]
        own: list[tuple[str, str]] = []
        d = os.path.dirname(path)
        while d and not (self.repo / d / "Makefile").is_file():
            d = os.path.dirname(d)
        if d and not d.startswith(("makefiles", "cpu", "boards")):
            own.append((d, ""))
        app = [(APP_CONTEXT, "")]
        root = [(".", "")]
        if scope == "Root":
            ordered = root + own + app
        elif scope == "App / help":
            ordered = app + root
        else:
            ordered = own + app + root
        ordered += [(c, "") for c in EXTRA_APP_CONTEXTS]
        # a make file that no default context includes: read it on its own
        if path and (self.repo / path).is_file() and \
                not os.path.basename(path) == "Makefile":
            ordered.append((os.path.dirname(path) or ".", path))
        return list(dict.fromkeys(ordered))

    def classify(self, target: str, scope: str,
                 evidence: str) -> tuple[Verdict, str]:
        contexts = self.contexts_for(scope, evidence)
        # pass 1: goal ':'; pass 2: the target as goal (files that are only
        # included for some goals, e.g. menuconfig, info-boards-features-*)
        for goal in (":", target):
            for board in dict.fromkeys((self.board, FALLBACK_BOARD)):
                for ctx, makefile in contexts:
                    v = self.classify_in(self.db(ctx, board, makefile, goal),
                                         target, frozenset())
                    if v:
                        where = ctx + (f" -f {makefile}" if makefile else "")
                        where += f" BOARD={board}"
                        if goal != ":":
                            where += " (goal-specific)"
                        return v, where
        return Verdict("?", "N0", "target not defined in any context"), ""


# --- static scan of declarations ------------------------------------------
DECL_RE = re.compile(r"^([A-Za-z0-9_./%$(){}-][^:=#\t]*?)\s*:{1,2}(?![=])")


def scan(repo: Path, rev: str | None = None) -> dict[str, str]:
    """Literal, named target declarations: name -> first file:line.

    rev=None scans the working tree (tracked and untracked, not ignored
    files); otherwise the given git revision."""
    cmd = ["git", "-C", str(repo), "grep", "-n", "-I"]
    cmd += ["--untracked"] if rev is None else []
    # ERE has no \t escape: put a literal tab into the bracket expression
    cmd += ["-E", "^[A-Za-z0-9_./-][^:=#\t]*:{1,2}([^=]|$)"]
    cmd += [] if rev is None else [rev]
    cmd += ["--", "*Makefile*", "*.mk"]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True,
                         errors="replace", check=False).stdout
    found: dict[str, str] = {}
    for line in sorted(out.splitlines()):
        if rev is not None:
            line = line[len(rev) + 1:]
        rel, num, content = line.split(":", 2)
        m = DECL_RE.match(content)
        if not m:
            continue
        for name in m.group(1).split():
            if any(c in name for c in "$%()*{}") or name.startswith("."):
                continue
            if "." in name and "/" not in name:   # file names (foo.o)
                continue
            found.setdefault(name, f"{rel}:{num}")
    return found


# --- I/O ---------------------------------------------------------------------
def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path | None, rows: list[dict[str, str]], fields: list[str]):
    f = sys.stdout if path is None else path.open("w", newline="")
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    if path is not None:
        f.close()


def cmd_classify(args) -> int:
    clf = Classifier(args.repo.resolve(), args.board)
    rows = []
    for item in read_inventory(args.inventory):
        v, ctx = clf.classify(item["target"], item.get("scope", ""),
                              item.get("evidence", ""))
        rows.append({"target": item["target"], "group": v.group,
                     "rule": v.rule, "context": ctx, "evidence": v.evidence})
    rows.sort(key=lambda r: r["target"])
    write_csv(args.output, rows,
              ["target", "group", "rule", "context", "evidence"])
    return 0


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[g] * cb[g] for g in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


def cmd_compare(args) -> int:
    ref = {r["target"]: r["group"] for r in read_inventory(args.inventory)}
    got = {r["target"]: r["group"] for r in read_inventory(args.result)}
    pairs = [(ref[t], got[t]) for t in sorted(ref) if t in got]
    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    labels = list(GROUPS) + ["?"]
    print(f"targets compared: {n}")
    print(f"agreement: {agree}/{n} = {agree / n:.3f}")
    print(f"Cohen's kappa: {cohen_kappa(pairs):.3f}")
    print("confusion (rows = reference, columns = rules):")
    print("ref\\rule " + " ".join(f"{g:>4}" for g in labels))
    for a in GROUPS:
        print(f"{a:>8} " + " ".join(
            f"{sum(1 for x, y in pairs if x == a and y == b):>4}"
            for b in labels))
    if args.list:
        for t in sorted(ref):
            if t in got and ref[t] != got[t]:
                print(f"DIFF {t}: reference {ref[t]} rules {got[t]}")
    return 0


def cmd_scan(args) -> int:
    for name, where in sorted(scan(args.repo.resolve()).items()):
        print(f"{name}\t{where}")
    return 0


def cmd_check_new(args) -> int:
    """Targets declared in the working tree but neither at the base revision
    nor in the inventory are new: classify them by the same rules and fail,
    so that the author adds them to the inventory with their group."""
    repo = args.repo.resolve()
    known = {r["target"] for r in read_inventory(args.inventory)}
    base = scan(repo, args.base)
    new = {n: w for n, w in scan(repo).items()
           if n not in base and n not in known}
    if not new:
        print(f"no new targets since {args.base}")
        return 0
    clf = Classifier(repo, args.board)
    failed = 0
    for name, where in sorted(new.items()):
        v, ctx = clf.classify(name, "", where)
        if v.group == "?":
            failed += 1
            print(f"NEW {name} ({where}): not callable in any known context "
                  f"(not functional or needs a new context)")
        else:
            print(f"NEW {name} ({where}): group {v.group} [{v.rule}] "
                  f"{v.evidence} (context {ctx})")
    print(f"{len(new)} new target(s): add them to {args.inventory.name} "
          "with the group shown above.", file=sys.stderr)
    return 1


def main() -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", type=Path, default=here.parents[2])
    p.add_argument("--board", default=DEFAULT_BOARD)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify")
    c.add_argument("--inventory", type=Path, default=here / "inventory.csv")
    c.add_argument("--output", type=Path)
    c.set_defaults(func=cmd_classify)
    c = sub.add_parser("compare")
    c.add_argument("--inventory", type=Path, default=here / "inventory.csv")
    c.add_argument("result", type=Path)
    c.add_argument("--list", action="store_true")
    c.set_defaults(func=cmd_compare)
    c = sub.add_parser("scan")
    c.set_defaults(func=cmd_scan)
    c = sub.add_parser("check-new")
    c.add_argument("--inventory", type=Path, default=here / "inventory.csv")
    c.add_argument("--base", default="master",
                   help="git revision to compare with (default: master)")
    c.set_defaults(func=cmd_check_new)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
