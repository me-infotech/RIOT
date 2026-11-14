#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Resolve modules, packages and features of a RIOT application without
Make (roadmap P6, decision D25).

Input: the dependency rules translated from Makefile.dep/Makefile.features
(translate_deps.py), the application's riot-app.yaml (configuration layer)
and the board. The rules are evaluated in Make's order (decision D25):

  1. Makefile.features (board, CPU, global features)
  2. defaultmodules_regular.inc.mk (DEFAULT_MODULE, Makefile.default)
  3. features check (FEATURES_USED)
  4. USEMODULE += DEFAULT_MODULE - DISABLE_MODULE
  5. repeat until USEMODULE, USEPKG, FEATURES_USED no longer change:
     Makefile.dep (root, board, CPU, sys, drivers, modules, packages),
     boards/Makefile.features, features check, features_modules.inc.mk
  6. finalisation (defaultmodules_no_recursive_deps, auto_init/periph_init,
     default modules again, defaultmodules_deps)

Output (JSON): modules, packages, features used/provided, CPU, and the
number of passes.

Usage: resolver.py <riot root> <rules.json> <riot-app.yaml> <board>
"""

import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import makeexpr  # noqa: E402
from makeexpr import _pattern_match, evaluate  # noqa: E402
from translate_deps import translate  # noqa: E402


class MakeError(Exception):
    pass


class State:
    """Make variables: name -> (flavor, text); flavor 'r' (recursive, `=`)
    or 's' (simple, `:=`)."""

    def __init__(self):
        self.vars: dict[str, tuple[str, str]] = {}
        self.exports: set[str] = set()
        # rules read so far: [targets, prerequisites (expanded), recipe lines]
        self.rules: list = []
        self.default_goal: str | None = None
        self.messages: list[tuple[str, str]] = []

    def raw(self, name):
        v = self.vars.get(name)
        return None if v is None else v[1]

    def get(self, name) -> str:
        v = self.vars.get(name)
        if v is None:
            return ""
        return evaluate(v[1], self.raw) if v[0] == "r" else v[1]

    def words(self, name) -> list[str]:
        return self.get(name).split()

    def expand(self, text: str) -> str:
        return evaluate(text, self.raw)

    def assign(self, name, op, text):
        cur = self.vars.get(name)
        if op == ":=":
            self.vars[name] = ("s", self.expand(text))
        elif op == "=":
            self.vars[name] = ("r", text)
        elif op == "?=":
            if cur is None:
                self.vars[name] = ("r", text)
        elif op == "+=":
            if cur is None:
                self.vars[name] = ("r", text)
            elif cur[0] == "s":
                self.vars[name] = ("s", (cur[1] + " " + self.expand(text)).strip())
            else:
                self.vars[name] = ("r", (cur[1] + " " + text).strip())

    def set_words(self, name, words):
        self.vars[name] = ("s", " ".join(words))


class Resolver:
    def __init__(self, root: str, rules: dict):
        self.root = os.path.abspath(root)
        self.rules = rules["files"]
        self.s = State()
        makeexpr.EVAL = self.eval_text

    def eval_text(self, text: str):
        """$(eval …): translate the text like a make file and run it."""
        unsupported: list = []
        items = translate(text, "$(eval)", unsupported)
        if unsupported:
            raise MakeError(f"$(eval) with unsupported content: {unsupported[0]['text']}")
        self.run(items, "$(eval)")

    # -- rule interpreter -----------------------------------------------------
    def cond(self, c: dict) -> bool:
        (kind, arg), = c.items()
        s = self.s
        if kind in ("any", "none"):
            var, pats = arg
            hit = any(_pattern_match(p, w) for w in s.words(var) for p in pats)
            return hit if kind == "any" else not hit
        if kind in ("any_out", "none_out"):
            var, pats = arg
            rest = [w for w in s.words(var)
                    if not any(_pattern_match(p, w) for p in pats)]
            return bool(rest) if kind == "any_out" else not rest
        if kind in ("eq", "ne"):
            var, val = arg
            same = s.get(var).strip() == val.strip()
            return same if kind == "eq" else not same
        if kind in ("def", "undef"):
            defined = bool((s.raw(arg) or "").strip())
            return defined if kind == "def" else not defined
        if kind == "expr":
            op, a, b = arg
            same = s.expand(a).strip() == s.expand(b).strip()
            return same if op == "ifeq" else not same
        raise MakeError(f"unknown condition {kind}")

    def record_rule(self, text: str):
        """Remember a rule (targets expanded when read, like Make)."""
        s = self.s
        depth, k = 0, 0
        for k, ch in enumerate(text):
            if ch in "({":
                depth += 1
            elif ch in ")}":
                depth -= 1
            elif ch == ":" and depth == 0:
                break
        targets = s.expand(text[:k]).split()
        rest = text[k + 1:].lstrip(":")
        if re.match(r"^\s*[\w.-]+\s*(\+=|:=|\?=|=)", rest):
            s.rules.append(None)         # target-specific variable: ignored
            return
        if ";" in rest:
            rest, inline = rest.split(";", 1)
        else:
            inline = None
        prereqs = s.expand(rest).replace("|", " ").split()
        s.rules.append([targets, prereqs, [inline] if inline else []])
        if s.default_goal is None:
            first = [t for t in targets if not t.startswith(".") and "%" not in t]
            if first:
                s.default_goal = first[0]

    def run(self, items: list, where: str):
        for it in items:
            if "if" in it:
                self.run(it["then"] if self.cond(it["if"]) else it["else"],
                         where)
            elif "assign" in it:
                text = it["expr"] if "expr" in it else " ".join(it["words"])
                self.s.assign(it["assign"], it["op"], text)
                if it["assign"] == ".DEFAULT_GOAL" and not self.s.get(".DEFAULT_GOAL").strip():
                    self.s.default_goal = None   # next target becomes default
                if it.get("export"):
                    self.s.exports.add(it["assign"])
            elif "export" in it:
                self.s.exports.update(self.s.expand(" ".join(it["export"])).split())
            elif "unexport" in it:
                self.s.exports.difference_update(it["unexport"])
            elif "include" in it or "include_expr" in it:
                text = it.get("include_expr") or " ".join(it["include"])
                for path in self.s.expand(text).split():
                    self.include(path, it["optional"], where)
            elif "message" in it:
                text = self.s.expand(it["text"])
                self.s.messages.append((it["message"], text))
                if it["message"] == "error":
                    raise MakeError(f"{where}:{it['line']}: {text}")
            elif "call" in it:
                self.s.expand(it["call"])        # side effects: messages
            elif "undefine" in it:
                self.s.vars.pop(it["undefine"].strip(), None)
            elif "rule" in it:
                self.record_rule(it["rule"])
            elif "recipe" in it:
                if self.s.rules and self.s.rules[-1] is not None:
                    self.s.rules[-1][2].append(it["recipe"])
            elif "noop" in it:
                pass
            elif "unsupported" in it:
                raise MakeError(f"{where}:{it['line']}: unsupported "
                                f"construct: {it['text']}")

    # makefiles that are part of the engine (implemented in Python) or only
    # define output helpers (colours, string functions are translated)
    ENGINE = {"makefiles/features_check.inc.mk": "features_check"}
    NO_EFFECT: set = set()   # all includes are evaluated (colour helpers
    #                          define functions used in recipes)

    def include(self, path: str, optional: bool, where: str = "-"):
        rel = os.path.relpath(os.path.normpath(path), self.root)
        if rel in self.ENGINE:
            getattr(self, self.ENGINE[rel])()
            return
        if rel in self.NO_EFFECT:
            return
        if rel in self.rules:
            self.s.assign("MAKEFILE_LIST", "+=", os.path.join(self.root, rel))
            self.run(self.rules[rel], rel)
        elif os.path.isfile(os.path.join(self.root, rel)):
            # not in the translation (e.g. a module Makefile, generated .d
            # dependency files): translate it now, like Make reads it
            unsupported: list = []
            items = translate(open(os.path.join(self.root, rel),
                                   errors="replace").read(), rel, unsupported)
            if unsupported:
                raise MakeError(f"{where}: include of {rel} with unsupported "
                                f"content: {unsupported[0]['text']}")
            self.rules[rel] = items
            self.s.assign("MAKEFILE_LIST", "+=", os.path.join(self.root, rel))
            self.run(items, rel)
        elif not optional:
            raise MakeError(f"{where}: missing include {rel}")

    # -- engine: what Make does in its own makefiles ------------------------------
    def features_check(self):
        """makefiles/features_check.inc.mk."""
        s = self.s
        provided = s.words("FEATURES_PROVIDED")
        s.assign("FEATURES_REQUIRED", "+=", " ".join(
            f for f in provided if f.startswith(("arch_", "bug_", "cpu_"))))
        required = s.words("FEATURES_REQUIRED")
        optional_used_prev = s.words("FEATURES_OPTIONAL_USED")
        used_so_far = sorted(set(required) | set(optional_used_prev))
        would_conflict = []
        for conflict in s.words("FEATURES_CONFLICT"):
            group = conflict.split(":")
            if set(group) & set(used_so_far):
                would_conflict += [f for f in group if f not in used_so_far]
        blacklist = s.words("FEATURES_BLACKLIST")
        usable = [f for f in provided
                  if f not in blacklist and f not in would_conflict]
        optional_only = sorted(set(s.words("FEATURES_OPTIONAL")) - set(required))
        optional_used = sorted(set(f for f in optional_only if f in usable))
        s.set_words("FEATURES_OPTIONAL_USED", optional_used)
        used_so_far = sorted(set(required) | set(optional_used))
        one_out_of = []
        for item in s.words("FEATURES_REQUIRED_ANY"):
            alts = item.split("|")
            pick = [f for f in alts if f in used_so_far] + \
                [f for f in alts if f in usable] + alts
            one_out_of.append(pick[0])
        s.set_words("FEATURES_USED", sorted(set(required) | set(one_out_of) |
                                            set(optional_used)))

    def state_key(self):
        s = self.s
        return (tuple(s.words("USEMODULE")), tuple(s.words("USEPKG")),
                tuple(s.words("FEATURES_USED")))

    def sort_vars(self, *names):
        for n in names:
            self.s.set_words(n, sorted(set(self.s.words(n))))

    def resolve(self, app: dict, board: str, max_passes: int = 50) -> dict:
        s, root = self.s, self.root
        base = {"RIOTBASE": root, "RIOTMAKE": f"{root}/makefiles",
                "RIOTCPU": f"{root}/cpu", "RIOTBOARD": f"{root}/boards",
                "RIOTPKG": f"{root}/pkg", "BOARD": board,
                "BOARDDIR": f"{root}/boards/{board}", "TOOLCHAIN": "gnu",
                "APPDIR": app["_appdir"], "OS": "Linux", "OS_ARCH": "x86_64"}
        for k, v in base.items():
            s.assign(k, ":=", v)
        keymap = {"usemodule": "USEMODULE", "usepkg": "USEPKG",
                  "disable_module": "DISABLE_MODULE",
                  "features_required": "FEATURES_REQUIRED",
                  "features_required_any": "FEATURES_REQUIRED_ANY",
                  "features_optional": "FEATURES_OPTIONAL",
                  "features_blacklist": "FEATURES_BLACKLIST"}
        for key, var in keymap.items():
            if app.get(key):
                s.assign(var, "+=", " ".join(app[key]))
        # scalar settings of riot-app.yaml (`?=` like the generated adapter;
        # the environment/command line is not modelled here)
        for key, var in {"develhelp": "DEVELHELP", "quiet": "QUIET",
                         "werror": "WERROR"}.items():
            if key in app:
                s.assign(var, "?=", str(app[key]))
        for var, val in (app.get("app_defaults") or {}).items():
            s.assign(var, "?=", str(val))
        # 1.-2.
        self.include(f"{root}/Makefile.features", False, "pipeline")
        self.include(f"{root}/makefiles/defaultmodules_regular.inc.mk",
                     False, "pipeline")
        # 3.-4.
        self.features_check()
        s.assign("USEMODULE", "+=", " ".join(
            m for m in s.words("DEFAULT_MODULE")
            if not any(_pattern_match(p, m) for p in s.words("DISABLE_MODULE"))))
        self.sort_vars("USEMODULE")
        # 5.
        passes = 0
        while True:
            passes += 1
            if passes > max_passes:
                raise MakeError("no fixpoint")
            old = self.state_key()
            pkg_paths = [f"{root}/pkg/{p}/" for p in s.words("USEPKG")
                         if os.path.isfile(f"{root}/pkg/{p}/Makefile")]
            s.set_words("PKG_PATHS", sorted(set(pkg_paths)))
            s.set_words("EXTERNAL_MODULE_PATHS", [])
            self.include(f"{root}/Makefile.dep", False, "pipeline")
            self.include(f"{root}/boards/Makefile.features", False, "pipeline")
            self.features_check()
            self.include(f"{root}/makefiles/features_modules.inc.mk", False,
                         "pipeline")
            self.sort_vars("USEMODULE", "USEPKG", "FEATURES_USED")
            if self.state_key() == old:
                break
        # 6.
        self.include(f"{root}/makefiles/defaultmodules_no_recursive_deps.inc.mk",
                     False, "pipeline")
        disable = s.words("DISABLE_MODULE")
        s.assign("USEMODULE", "+=", " ".join(
            m for m in ("auto_init", "periph_init")
            if not any(_pattern_match(p, m) for p in disable)))
        if "auto_init" not in s.words("USEMODULE"):
            s.assign("DISABLE_MODULE", "+=", "auto_init_%")
        if "periph_init" not in s.words("USEMODULE"):
            s.assign("DISABLE_MODULE", "+=", "periph_init_%")
        disable = s.words("DISABLE_MODULE")
        s.assign("USEMODULE", "+=", " ".join(
            m for m in s.words("DEFAULT_MODULE")
            if not any(_pattern_match(p, m) for p in disable)))
        self.include(f"{root}/makefiles/defaultmodules_deps.inc.mk", False,
                     "pipeline")
        self.sort_vars("USEMODULE", "DEFAULT_MODULE")
        return {"board": board, "cpu": s.get("CPU").strip(),
                "cpu_model": s.get("CPU_MODEL").strip(),
                "modules": s.words("USEMODULE"), "packages": sorted(set(s.words("USEPKG"))),
                "features_used": s.words("FEATURES_USED"),
                "features_provided": sorted(set(s.words("FEATURES_PROVIDED"))),
                "passes": passes,
                "messages": [list(m) for m in s.messages]}


def main() -> int:
    root, rules_path, app_path, board = sys.argv[1:5]
    rules = json.load(open(rules_path))
    app = yaml.safe_load(open(app_path)) or {}
    app["_appdir"] = os.path.dirname(os.path.abspath(app_path))
    try:
        result = Resolver(root, rules).resolve(app, board)
    except MakeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
