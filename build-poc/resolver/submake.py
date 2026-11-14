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

    def run_dir(self, directory: str, makefile: str | None = None,
                extra: dict | None = None, env_extra: dict | None = None):
        directory = os.path.normpath(directory)
        key = (directory, makefile, tuple(sorted((extra or {}).items())))
        if key in self.visited:
            return
        self.visited.add(key)
        r = Resolver(self.top.root, {"files": {}})
        r.rules = self.rules["files"]
        s = r.s
        for k, v in self.env.items():
            s.vars[k] = ("r", v.replace("$", "$$"))   # environment variables
        s.exports = set(self.env)
        for k, v in (env_extra or {}).items():
            s.vars[k] = ("r", v.replace("$", "$$"))   # only this sub-make
        for k, v in (extra or {}).items():
            s.assign(k, ":=", v)                      # command-line variables
        s.assign("CURDIR", ":=", directory)
        s.assign("MAKEFILE_LIST", ":=", "")
        s.assign("MAKE", ":=", "make")
        makeexpr.CWD = directory
        mk = makefile or os.path.join(directory, "Makefile")
        s.assign("MAKEFILE_LIST", "+=", mk)
        r.run(rules_of(mk, self.rules), os.path.relpath(mk, self.top.root))
        module = s.get("MODULE").strip()
        cc = s.get("CC").strip()
        if not cc:
            raise MakeError(f"{directory}: CC is empty")
        # Makefile.base: `$(OBJC_LTO): CFLAGS+=$(LTOFLAGS)`, recipe
        # `$(CC) $(CFLAGS) $(RCFLAGS) $(INCLUDES) -MQ … -c -o $@ $<`
        flags_nolto = shlex.split(s.expand("$(CFLAGS) $(RCFLAGS) $(INCLUDES)"))
        flags_lto = shlex.split(s.expand(
            "$(CFLAGS) $(LTOFLAGS) $(RCFLAGS) $(INCLUDES)"))
        for srcvar, objvar, fl in (("SRC", "OBJC_LTO", flags_lto),
                                   ("SRC_NOLTO", "OBJC_NOLTO", flags_nolto)):
            srcs, objs = s.words(srcvar), s.words(objvar)
            if len(srcs) != len(objs):
                raise MakeError(f"{directory}: {srcvar}/{objvar} differ")
            for src, obj in zip(srcs, objs):
                self.objects.append({
                    "compiler": cc,
                    "source": os.path.normpath(os.path.join(directory, src)),
                    "object": obj, "module": module, "flags": fl})
        for name in ("SRCXX", "ASMSRC", "ASSMSRC", "GENSRC"):
            if s.words(name):
                raise MakeError(f"{directory}: {name} not supported yet")
        for d in s.words("DIRS"):
            self.run_dir(d if os.path.isabs(d) else os.path.join(directory, d))
        makeexpr.CWD = self.top.root

    def run_package(self, pkg_dir: str):
        """`all` recipe of pkg/<name>/Makefile: sub-makes with Makefile.base."""
        r = Resolver(self.top.root, {"files": {}})
        r.rules = self.rules["files"]
        s = r.s
        for k, v in self.env.items():
            s.vars[k] = ("r", v.replace("$", "$$"))
        s.exports = set(self.env)
        s.assign("CURDIR", ":=", pkg_dir)
        makeexpr.CWD = pkg_dir
        mk = os.path.join(pkg_dir, "Makefile")
        items = rules_of(mk, self.rules)
        r.run(items, os.path.relpath(mk, self.top.root))
        in_all = False
        for it in items:
            if "rule" in it:
                in_all = it["rule"].split(":")[0].split() == ["all"]
                continue
            if in_all and "recipe" in it:
                cmd = shlex.split(s.expand(it["recipe"]).lstrip("@+-"))
                if "-C" not in cmd:
                    continue
                d = cmd[cmd.index("-C") + 1]
                mf = cmd[cmd.index("-f") + 1] if "-f" in cmd else None
                extra = dict(a.split("=", 1) for a in cmd if "=" in a and
                             not a.startswith("-"))
                # the sub-make inherits the package make's exported
                # variables, e.g. pkg.mk's `CFLAGS += -Wno-maybe-uninitialized`
                pkg_env = {n: s.get(n) for n in s.exports if n in s.vars}
                self.run_dir(d, mf, extra, env_extra=pkg_env)


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
               env_extra=app_env)
    for p in s.words("PKG_PATHS"):
        sm.run_package(p.rstrip("/"))
    sm.objects.sort(key=lambda o: o["object"])
    json.dump({"objects": sm.objects}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
