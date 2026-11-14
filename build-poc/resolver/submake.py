#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Reproduce the per-module builds of RIOT without Make (D26): starting
from the application, every directory in DIRS is evaluated like a sub-make
(its Makefile + Makefile.base, translated to rules, with the exported
variables of the top level), giving the object files, their sources and the
exact compile flags (`$(CFLAGS) $(RCFLAGS) $(INCLUDES)`, Makefile.base).
Packages are built the way their Makefile's `all` recipe says
(`$(MAKE) -C <dir> -f $(RIOTBASE)/Makefile.base [MODULE=…]`).

Usage: submake.py <riot root> <rules.json> <riot-app.yaml> <board> > objects.json
"""

import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flags  # noqa: E402
import makeexpr  # noqa: E402
from resolver import MakeError, Resolver, State  # noqa: E402
from translate_deps import translate  # noqa: E402

_TRANSLATED: dict = {}


def rules_of(path: str, rules: dict) -> list:
    """Rules of a make file: from the translation, or translated now."""
    root = rules["_root"]
    rel = os.path.relpath(path, root)
    if rel in rules["files"]:
        return rules["files"][rel]
    if path not in _TRANSLATED:
        unsupported: list = []
        _TRANSLATED[path] = translate(open(path).read(), rel, unsupported)
        if unsupported:
            raise MakeError(f"{rel}: unsupported: {unsupported[0]['text']}")
    return _TRANSLATED[path]


class SubMake:
    def __init__(self, top: Resolver, rules: dict):
        self.top = top
        self.rules = rules
        # environment of every sub-make: the exported variables, expanded
        self.env = {n: top.s.get(n) for n in sorted(top.s.exports)
                    if n in top.s.vars}
        self.objects: list = []
        self.visited: set = set()
        self.package_objects: dict = {}

    def run_dir(self, directory: str, makefile: str | None = None,
                cmdvars: dict | None = None, env: dict | None = None):
        """One sub-make: environment = the parent's exported variables,
        command-line variables protected and passed on (MAKEFLAGS)."""
        directory = os.path.normpath(directory)
        env = self.env if env is None else env
        cmdvars = cmdvars or {}
        key = (directory, makefile, tuple(sorted(cmdvars.items())))
        if key in self.visited:
            return
        self.visited.add(key)
        if not os.path.isdir(directory):
            raise MakeError(f"sub-make directory {directory} does not exist "
                            "(prerequisites not prepared?)")
        r = Resolver(self.top.root, {"files": {}})
        r.rules = self.rules["files"]
        s = r.s
        for k, v in env.items():
            s.vars[k] = ("r", v.replace("$", "$$"))   # environment variables
        s.exports = set(env)
        for k, v in cmdvars.items():
            s.set_cmdline(k, v)                       # command-line variables
        s.assign("CURDIR", ":=", directory, override=True)
        s.assign("MAKEFILE_LIST", ":=", "", override=True)
        s.assign("MAKE", ":=", "make", override=True)
        makeexpr.CWD = directory
        mk = makefile or os.path.join(directory, "Makefile")
        s.assign("MAKEFILE_LIST", "+=", mk, override=True)
        r.run(rules_of(mk, self.rules), os.path.relpath(mk, self.top.root))
        module = s.get("MODULE").strip()
        cc = s.get("CC").strip()
        if not cc:
            raise MakeError(f"{directory}: CC is empty")
        # Makefile.base recipe: `$(CC) $(CFLAGS) $(RCFLAGS) $(INCLUDES) -MQ …
        # -c -o $@ $<`; target-specific variables of the object (e.g.
        # `$(OBJC_LTO): CFLAGS+=$(LTOFLAGS)`) apply while it is compiled
        for srcvar, objvar in (("SRC", "OBJC_LTO"), ("SRC_NOLTO", "OBJC_NOLTO")):
            srcs, objs = s.words(srcvar), s.words(objvar)
            if len(srcs) != len(objs):
                raise MakeError(f"{directory}: {srcvar}/{objvar} differ")
            for src, obj in zip(srcs, objs):
                restore = r.target_overlay(obj)
                try:
                    fl = shlex.split(s.expand("$(CFLAGS) $(RCFLAGS) $(INCLUDES)"))
                finally:
                    restore()
                self.objects.append({
                    "compiler": cc,
                    "source": os.path.normpath(os.path.join(directory, src)),
                    "object": obj, "module": module, "flags": fl})
        for name in ("SRCXX", "ASMSRC", "ASSMSRC", "GENSRC"):
            if s.words(name):
                raise MakeError(f"{directory}: {name} not supported yet")
        # children inherit this sub-make's exported variables (e.g. a
        # `CFLAGS += …` before `DIRS += …`), not only the top level's
        child_env = {n: s.get(n) for n in s.exports if n in s.vars}
        for d in s.words("DIRS"):
            self.run_dir(d if os.path.isabs(d) else os.path.join(directory, d),
                         None, dict(s.cmdline), child_env)
        makeexpr.CWD = self.top.root

    def run_package(self, pkg_dir: str):
        """`make -C pkg/<name>` (pkg-build): its default goal is made with
        the recipe runner of prestep.py; every recursive make it reaches is
        a module build (Makefile.base) and evaluated here; any other command
        stops the run (package builds that run other tools are not
        supported)."""
        from prestep import Context, Runner   # noqa: avoid import cycle

        def on_make(cwd, makefile, goals, env, cmdvars):
            if goals and goals != ["all"]:
                raise MakeError(f"package sub-make with goals {goals} in {cwd}")
            self.run_dir(cwd, makefile, cmdvars, env)

        goal = {}

        def on_command(ctx, cmd, target):
            # preparation steps (prerequisites of the goal) run normally;
            # the goal's own recipe may only contain module builds
            if target == goal.get("name"):
                raise MakeError(f"package build in {ctx.cwd} runs a command "
                                f"that is not a module build: {cmd[:120]}")
            return False

        runner = Runner(self.top.root, self.rules, on_make, on_command)
        r = runner.state(pkg_dir, None, self.env, {})
        ctx = Context(r, pkg_dir)
        before = len(self.objects)
        goal["name"] = r.s.default_goal
        runner.build(ctx, r.s.default_goal)
        self.package_objects[os.path.basename(pkg_dir)] = len(self.objects) - before


def main() -> int:
    root, rules_path, app_path, board = sys.argv[1:5]
    rules = json.load(open(rules_path))
    rules["_root"] = os.path.abspath(root)
    sys.argv = [sys.argv[0], root, rules_path, app_path, board, "DIRS"]
    top = flags.evaluate(root, rules, app_path, board)
    sm = SubMake(top, rules)
    s = top.s
    appdir = os.path.dirname(os.path.abspath(app_path))
    # application module: DIRS and APPLICATION_* are passed in the
    # environment (Makefile.include, $(APPLICATION_MODULE).module)
    app_env = {"DIRS": s.get("DIRS"), "APPLICATION_BLOBS": s.get("BLOBS"),
               "APPLICATION_SRC": s.get("SRC"),
               "APPLICATION_SRCXX": s.get("SRCXX"),
               "APPLICATION_ASMSRC": s.get("ASMSRC"),
               "APPLICATION_ASSMSRC": s.get("ASSMSRC")}
    sm.run_dir(appdir, os.path.join(root, "makefiles/application.inc.mk"),
               None, dict(sm.env, **app_env))
    for p in s.words("PKG_PATHS"):
        sm.run_package(p.rstrip("/"))
    sm.objects.sort(key=lambda o: o["object"])
    json.dump({"objects": sm.objects}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
