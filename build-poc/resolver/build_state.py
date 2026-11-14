#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Write resolved-state.json (the input of gen_cmake.py / gen_meson.py)
without Make (D26): modules, CPU, objects with their exact compile flags
(submake.py), the link command (`$(LINK) <objects> $(ARCHIVES_GROUP)
$(LINKFLAGS) $(LINKFLAGPREFIX)-Map=… -o $(ELFFILE)`, Makefile.include) and
the runtime variables of the 2B targets.

Usage: build_state.py <riot root> <rules.json> <riot-app.yaml> <board>
       > resolved-state.json
"""

import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flags  # noqa: E402
import makeexpr  # noqa: E402
from resolver import MakeError  # noqa: E402
from submake import SubMake  # noqa: E402

RUNTIME = ("FLASHER", "FFLAGS", "TERMPROG", "TERMFLAGS", "PORT", "SIZE",
           "ELFFILE")


def main() -> int:
    root, rules_path, app_path, board = sys.argv[1:5]
    rules = json.load(open(rules_path))
    rules["_root"] = os.path.abspath(root)
    try:
        top = flags.evaluate(root, rules, app_path, board)
        s = top.s
        sm = SubMake(top, rules)
        appdir = os.path.dirname(os.path.abspath(app_path))
        app_env = {"DIRS": s.get("DIRS"), "APPLICATION_BLOBS": s.get("BLOBS"),
                   "APPLICATION_SRC": s.get("SRC"),
                   "APPLICATION_SRCXX": s.get("SRCXX"),
                   "APPLICATION_ASMSRC": s.get("ASMSRC"),
                   "APPLICATION_ASSMSRC": s.get("ASSMSRC")}
        sm.run_dir(appdir, os.path.join(root, "makefiles/application.inc.mk"),
                   env_extra=app_env)
        for p in s.words("PKG_PATHS"):
            sm.run_package(p.rstrip("/"))
        makeexpr.CWD = appdir
        link_flags = shlex.split(s.expand(
            "$(ARCHIVES_GROUP) $(LINKFLAGS) $(LINKFLAGPREFIX)-Map=$(BINDIR)/$(APPLICATION).map"))
        objects = sorted(({k: o[k] for k in ("compiler", "source", "object", "flags")}
                          for o in sm.objects), key=lambda o: o["object"])
        state = {"schema": "riot-resolved-build/0",
                 "application": s.get("APPLICATION").strip(),
                 "board": board, "cpu": s.get("CPU").strip(),
                 "modules": sorted(set(s.words("USEMODULE"))),
                 "objects": objects,
                 "link": {"linker": s.get("LINK").strip(), "flags": link_flags,
                          "output": s.get("ELFFILE").strip()},
                 "runtime": {v: s.get(v).strip() for v in RUNTIME},
                 "produced_by": "build-poc/resolver (without Make)"}
    except (MakeError, makeexpr.UnsupportedExpr) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    json.dump(state, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
