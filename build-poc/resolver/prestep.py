#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Run the build prerequisites of a RIOT application without Make (D26):
the targets in BUILDDEPS (package preparation, vendor headers, riotbuild.h,
preprocessor_successor.h).

RIOT has no stand-alone scripts for these steps, only recipes in its make
files (pkg/pkg.mk, Makefile.include, …). This is a minimal recipe runner:
it takes the rules read from the translated make files and remakes a
target like Make does — prerequisites first (order-only ones do not cause
a remake), then the recipe if the target does not exist, a prerequisite is
newer, or FORCE — and runs every command unchanged with /bin/sh in the
environment Make would export (exported variables expanded), applying
target-specific variables. A recursive `$(MAKE) [-C dir] [-f file]
[goal] [VAR=value]` at the start of a command is not passed to Make: the
named make file is evaluated from the translated rules (command-line
variables are protected and passed on, like MAKEFLAGS). Safety: `make`
anywhere else in a command and `rm -r`/`rm -f` outside the build
directories stop the run.

Rules: explicit (an explicit rule without recipe takes the recipe of a
matching pattern rule), static pattern rules, double-colon rules (each
with its own recipe and prerequisites), pattern rules (shortest stem
first; only a rule whose prerequisites exist, ought to exist or can be
made). Not modelled: parallel execution, .SECONDEXPANSION, .ONESHELL,
suffix rules, built-in implicit rules, VPATH.

Usage: prestep.py <riot root> <rules.json> <riot-app.yaml> <board>
"""

import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flags  # noqa: E402
import makeexpr  # noqa: E402
from resolver import MakeError, Resolver  # noqa: E402

MAKE_CALL = re.compile(r'^((?:[A-Za-z_]\w*=(?:"[^"]*"|\S*)\s+)*)"?make"?(\s.*|)$', re.S)
MAKE_ELSEWHERE = re.compile(r'(?:^|[\s;&|(`"$])make(?:\s|"|$)')
LOG: list = []


class Context:
    """One make invocation: its evaluated state and rules."""

    def __init__(self, resolver: Resolver, cwd: str, level: int = 0):
        self.r = resolver
        self.s = resolver.s
        self.cwd = cwd
        self.level = level              # MAKELEVEL of this make
        self.done: dict = {}

    @staticmethod
    def _stem(pattern: str, target: str):
        if not makeexpr._pattern_match(pattern, target):
            return None
        pre, post = pattern.split("%", 1)
        return target[len(pre):len(target) - len(post) or None]

    @staticmethod
    def _subst(pattern_words: list, stem: str) -> list:
        return [p.replace("%", stem, 1) for p in pattern_words]

    def mentioned(self, name: str) -> bool:
        """Target or prerequisite of an explicit rule ("ought to exist")."""
        for rule in self.s.rules:
            if not rule:
                continue
            if name in rule[0] and "%" not in name:
                return True
            if not rule[5] and name in rule[1] + rule[3]:
                return True
        return False

    def can_make(self, name: str, depth: int = 0) -> bool:
        """Exists, ought to exist, or can be made by a pattern rule."""
        path = name if os.path.isabs(name) else os.path.join(self.cwd, name)
        if os.path.exists(path) or self.mentioned(name):
            return True
        return depth < 4 and self.pattern_rule(name, depth + 1) is not None

    def pattern_rule(self, target: str, depth: int = 0):
        """(prereqs, order-only, recipe, stem) of the pattern rule Make
        would choose: among the rules with a recipe whose target pattern
        matches (shortest stem first, then in order), the first one whose
        prerequisites all exist, ought to exist or can be made."""
        candidates = []
        for k, rule in enumerate(self.s.rules):
            if not rule or rule[5] or not rule[2]:
                continue                  # static, or no recipe (cancels)
            for t in rule[0]:
                stem = self._stem(t, target) if "%" in t else None
                if stem is not None:
                    candidates.append((len(stem), k, rule, stem))
                    break
        for _, _, rule, stem in sorted(candidates, key=lambda c: c[:2]):
            prereqs = self._subst(rule[1], stem)
            if all(self.can_make(p, depth) for p in prereqs):
                return prereqs, self._subst(rule[3], stem), rule[2], stem
        return None

    def find(self, target: str):
        """List of (prereqs, order-only, recipe, stem) for target, one entry
        per rule that is run: explicit rules (all their prerequisites, the
        recipe of the one that has one; if none has a recipe, the recipe of
        a matching pattern rule), static pattern rules, or one entry per
        double-colon rule (each with its own recipe); else the pattern
        rule; None if there is no rule."""
        prereqs, order, recipe, stem, found = [], [], [], "", False
        double = []
        for rule in self.s.rules:
            if not rule or target not in rule[0]:
                continue
            if rule[4]:
                double.append((rule[1], rule[3], rule[2], ""))
                continue
            found = True
            if rule[5]:                   # static pattern rule
                st = self._stem(rule[5], target)
                if st is None:
                    st = target            # Make: warning, no prerequisites
                else:
                    prereqs += self._subst(rule[1], st)
                    order += self._subst(rule[3], st)
                stem = st
            else:
                prereqs += rule[1]
                order += rule[3]
            if rule[2]:
                recipe = rule[2]
        if double and found:
            raise MakeError(f"target file '{target}' has both : and :: entries")
        if double:
            return double
        if found:
            if not recipe:
                implicit = self.pattern_rule(target)
                if implicit:
                    prereqs += implicit[0]
                    order += implicit[1]
                    recipe, stem = implicit[2], implicit[3]
            return [(prereqs, order, recipe, stem)]
        implicit = self.pattern_rule(target)
        return [implicit] if implicit else None


def mtime(path: str):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


class Runner:
    """Minimal Make-like runner. on_make(cwd, makefile, goals, env,
    cmdvars) handles recursive makes (default: evaluate and build here);
    on_command(ctx, cmd) can refuse commands (used for package builds)."""

    def __init__(self, root: str, rules: dict, on_make=None, on_command=None):
        self.root = root
        self.rules = rules
        self.on_make = on_make or self.make
        self.on_command = on_command
        self.current = ""

    def state(self, cwd: str, makefile: str | None, env: dict, cmdvars: dict,
              goals: list | None = None):
        r = Resolver(self.root, {"files": {}})
        r.rules = self.rules["files"]
        s = r.s
        # MAKELEVEL: from the environment, one more than the parent's
        r.level = int(env.get("MAKELEVEL", "0")) + 1
        env = {k: v for k, v in env.items() if k != "MAKELEVEL"}
        for k, v in env.items():
            s.set_env(k, v.replace("$", "$$"))       # environment
        s.exports = set(env)
        s.set_env("MAKELEVEL", str(r.level))
        for k, v in cmdvars.items():
            s.set_cmdline(k, v)                       # command line
        if goals:
            s.set_simple("MAKECMDGOALS", " ".join(goals), "default")
        s.set_simple("CURDIR", cwd)
        s.set_simple("MAKE", "make", "default")
        makeexpr.CWD = cwd
        mk = makefile or os.path.join(cwd, "Makefile")
        if not os.path.isabs(mk):
            mk = os.path.join(cwd, mk)
        if not os.path.isdir(cwd):
            raise MakeError(f"directory {cwd} does not exist")
        r.include(mk, False, "prestep")
        return r

    def make(self, cwd, makefile, goals, env, cmdvars):
        r = self.state(cwd, makefile, env, cmdvars, goals)
        ctx = Context(r, cwd, r.level)
        for g in goals or [r.s.default_goal]:
            self.build(ctx, g)

    def build(self, ctx: Context, target: str) -> bool:
        """Make target; True if it was remade (its recipe ran)."""
        if target in ctx.done:
            return ctx.done[target]
        ctx.done[target] = False
        rules = ctx.find(target)
        path = target if os.path.isabs(target) else os.path.join(ctx.cwd, target)
        if rules is None:
            if target == "FORCE" or os.path.exists(path):
                return False
            raise MakeError(f"no rule to make {target} (in {ctx.cwd})")
        double = any(r and r[4] and target in r[0] for r in ctx.s.rules)
        remade_any = False
        for prereqs, order, recipe, stem in rules:
            newer = double and not prereqs   # `t::` without prerequisites
            for p in prereqs:
                if p == "FORCE":
                    newer = True
                    continue
                remade = self.build(ctx, p)
                ppath = p if os.path.isabs(p) else os.path.join(ctx.cwd, p)
                pt, tt = mtime(ppath), mtime(path)
                if (pt is None and remade) or (pt is not None and tt is not None and pt > tt):
                    newer = True
            for o in order:
                self.build(ctx, o)        # order-only: never causes a remake
            if mtime(path) is not None and not newer:
                continue
            self.run_recipe(ctx, target, prereqs, recipe, stem)
            remade_any = True
        ctx.done[target] = remade_any
        return remade_any

    def run_recipe(self, ctx: Context, target, prereqs, recipe, stem):
        self.current = target
        restore = ctx.r.target_overlay(target)
        makeexpr.AUTOMATIC = {"@": target, "<": prereqs[0] if prereqs else "",
                              "^": " ".join(dict.fromkeys(prereqs)), "*": stem}
        try:
            lines = [ctx.s.expand(line) for line in recipe]
            env = self.env_of(ctx)
        finally:
            makeexpr.AUTOMATIC = {}
            restore()
        for line in lines:
            # several commands per line only through real newlines
            # ($(NEWLINE)); backslash-newline continues the command
            for part in re.split(r"(?<!\\)\n", line):
                self.run_line(ctx, part, env)

    def env_of(self, ctx: Context) -> dict:
        """The environment Make gives a recipe: its own environment plus
        the exported variables, expanded."""
        env = dict(os.environ)
        for n in ctx.s.exports:
            if n in ctx.s.vars:
                env[n] = ctx.s.get(n)
        env["MAKELEVEL"] = str(ctx.level + 1)
        return env

    def check_rm(self, ctx: Context, cmd: str):
        """Refuse `rm -r`/`rm -f` outside the build directories."""
        for m in re.finditer(r"(?:^|[;&|]\s*)rm\s+([^;&|]*)", cmd):
            args = shlex.split(m.group(1))
            if not any(a.startswith("-") and ("r" in a.lower() or "f" in a)
                       for a in args):
                continue
            allowed = [ctx.s.get(v).strip() for v in ("BUILD_DIR", "BINDIRBASE",
                                                      "PKGDIRBASE")]
            allowed = [os.path.normpath(a) for a in allowed if a]
            for a in args:
                if a.startswith("-"):
                    continue
                full = os.path.normpath(a if os.path.isabs(a)
                                        else os.path.join(ctx.cwd, a))
                if not any(full == d or full.startswith(d + os.sep)
                           for d in allowed):
                    raise MakeError(f"refusing to remove {full} (outside "
                                    f"{', '.join(allowed)}): {cmd[:120]}")

    def run_line(self, ctx: Context, line: str, env: dict):
        cmd = line.strip()
        ignore = False
        while cmd[:1] in ("@", "-", "+"):
            ignore |= cmd[0] == "-"
            cmd = cmd[1:].lstrip()
        if not cmd:
            return
        m = MAKE_CALL.match(cmd)
        if m:
            env_prefix = dict(re.findall(r'([A-Za-z_]\w*)=("[^"]*"|\S*)', m.group(1)))
            args = shlex.split(m.group(2))
            cwd, mk, goals = ctx.cwd, None, []
            cmdvars = dict(ctx.s.cmdline)          # MAKEFLAGS: passed on
            k = 0
            while k < len(args):
                a = args[k]
                if a == "-C":
                    cwd = args[k + 1]
                    k += 2
                    continue
                if a == "-f":
                    mk = args[k + 1]
                    k += 2
                    continue
                if a.startswith("-"):
                    k += 1
                    continue
                if "=" in a:
                    n, v = a.split("=", 1)
                    cmdvars[n] = v
                else:
                    goals.append(a)
                k += 1
            child_env = {n: ctx.s.get(n) for n in ctx.s.exports if n in ctx.s.vars}
            child_env.update({k: v.strip('"') for k, v in env_prefix.items()})
            child_env["MAKELEVEL"] = str(ctx.level)    # the child adds one
            LOG.append(f"[make] -C {cwd} -f {mk} {' '.join(goals)}")
            self.on_make(os.path.normpath(os.path.join(ctx.cwd, cwd)), mk,
                         goals, child_env, cmdvars)
            makeexpr.CWD = ctx.cwd
            return
        if MAKE_ELSEWHERE.search(cmd):
            raise MakeError(f"recipe runs make inside a command: {cmd[:120]}")
        if self.on_command and self.on_command(ctx, cmd, self.current):
            return                        # handled (or refused) by the caller
        self.check_rm(ctx, cmd)
        LOG.append(cmd[:200])
        res = subprocess.run(["/bin/sh", "-c", cmd], cwd=ctx.cwd, env=env)
        if res.returncode != 0 and not ignore:
            raise MakeError(f"command failed ({res.returncode}): {cmd[:200]}")


def main() -> int:
    root, rules_path, app_path, board = sys.argv[1:5]
    rules = json.load(open(rules_path))
    try:
        top = flags.evaluate(root, rules, app_path, board)
        runner = Runner(root, rules)
        ctx = Context(top, os.path.dirname(os.path.abspath(app_path)))
        for target in top.s.words("BUILDDEPS"):
            runner.build(ctx, target)
    except (MakeError, makeexpr.UnsupportedExpr) as e:
        print(f"error: {e}", file=sys.stderr)
        print("\n".join(LOG[-15:]), file=sys.stderr)
        return 1
    print("\n".join(LOG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
