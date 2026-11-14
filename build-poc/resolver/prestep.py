#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Run the build prerequisites of a RIOT application without Make (D26):
the targets in BUILDDEPS (package preparation, vendor headers, riotbuild.h,
preprocessor_successor.h).

RIOT has no stand-alone scripts for these steps, only recipes in its make
files (pkg/pkg.mk, Makefile.include, …). This is a minimal recipe runner:
it takes the rules read from the translated make files, runs the recipes of
a target and of its prerequisites in dependency order, and runs every
command in them unchanged with /bin/sh (git, genconfigheader.sh,
lazysponge, generate_pp_successor_header.sh, cp, …). A recursive
`$(MAKE) [-C dir] [-f file] [goal] [VAR=value]` in a recipe is not passed
to Make: the named make file is evaluated from the translated rules and its
goal is run the same way.

Not modelled: time stamps beyond "the target file exists and no
prerequisite was remade", parallel execution, .SECONDEXPANSION.

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

MAKE_CALL = re.compile(r'^((?:[A-Za-z_]\w*=(?:"[^"]*"|\S*)\s+)*)"?make"?(\s.*|)$')
LOG: list = []


class Context:
    """One make invocation: its evaluated state and rules."""

    def __init__(self, resolver: Resolver, cwd: str):
        self.r = resolver
        self.s = resolver.s
        self.cwd = cwd
        self.done: dict = {}

    def find(self, target: str):
        """(prereqs, recipe, stem) for target: explicit rules first (all
        their prerequisites, the recipe of the one that has one), then
        pattern rules."""
        prereqs, recipe, found = [], [], False
        for rule in self.s.rules:
            if rule and target in rule[0]:
                found = True
                prereqs += rule[1]
                if rule[2]:
                    recipe = rule[2]
        if found:
            return prereqs, recipe, ""
        for rule in self.s.rules:
            if not rule:
                continue
            for t in rule[0]:
                if "%" in t and makeexpr._pattern_match(t, target):
                    pre, post = t.split("%", 1)
                    stem = target[len(pre):len(target) - len(post) or None]
                    return [p.replace("%", stem) for p in rule[1]], rule[2], stem
        return None


class Runner:
    def __init__(self, root: str, rules: dict):
        self.root = root
        self.rules = rules

    def make(self, cwd: str, makefile: str | None, goals: list,
             env: dict, cmdvars: dict):
        r = Resolver(self.root, {"files": {}})
        r.rules = self.rules["files"]
        s = r.s
        for k, v in env.items():
            s.vars[k] = ("r", v.replace("$", "$$"))
        s.exports = set(env)
        for k, v in cmdvars.items():
            s.assign(k, ":=", v)
        s.assign("CURDIR", ":=", cwd)
        s.assign("MAKE", ":=", "make")
        makeexpr.CWD = cwd
        mk = makefile or os.path.join(cwd, "Makefile")
        if not os.path.isabs(mk):
            mk = os.path.join(cwd, mk)
        r.include(mk, False, "prestep")
        ctx = Context(r, cwd)
        for g in goals or [s.default_goal]:
            self.build(ctx, g)

    def build(self, ctx: Context, target: str) -> bool:
        """Make target; return True if its recipe ran."""
        if target in ctx.done:
            return ctx.done[target]
        ctx.done[target] = False
        rule = ctx.find(target)
        if rule is None:
            if target == "FORCE" or os.path.exists(target) or \
                    os.path.exists(os.path.join(ctx.cwd, target)):
                return False
            raise MakeError(f"no rule to make {target} (in {ctx.cwd})")
        prereqs, recipe, stem = rule
        remade = False
        for p in prereqs:
            if p == "FORCE":
                remade = True
                continue
            remade |= self.build(ctx, p)
        path = target if os.path.isabs(target) else os.path.join(ctx.cwd, target)
        if os.path.exists(path) and not remade:
            return False
        makeexpr.AUTOMATIC = {"@": target, "<": prereqs[0] if prereqs else "",
                              "^": " ".join(dict.fromkeys(prereqs)), "*": stem}
        try:
            lines = [ctx.s.expand(line) for line in recipe]
        finally:
            makeexpr.AUTOMATIC = {}
        # one command per recipe line; a line may hold several commands
        # separated by real newlines ($(NEWLINE) in $(foreach)), while a
        # backslash-newline continues the same command
        for line in lines:
            for part in re.split(r"(?<!\\)\n", line):
                self.run_line(ctx, part)
        ctx.done[target] = True
        return True

    def run_line(self, ctx: Context, line: str):
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
            cwd, mk, goals, cmdvars = ctx.cwd, None, [], {}
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
            env = {n: ctx.s.get(n) for n in ctx.s.exports if n in ctx.s.vars}
            env.update({k: v.strip('"') for k, v in env_prefix.items()})
            LOG.append(f"[make] -C {cwd} -f {mk} {' '.join(goals)}")
            self.make(os.path.normpath(os.path.join(ctx.cwd, cwd)), mk, goals,
                      env, cmdvars)
            makeexpr.CWD = ctx.cwd
            return
        LOG.append(cmd[:200])
        res = subprocess.run(["/bin/sh", "-c", cmd], cwd=ctx.cwd)
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
