#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Export the resolved build state of one application/board from a verbose
Make build log (`make QUIET=0 -j1 all` after `make clean`).

Roadmap P6, scenario S2: Make stays the (transitional) resolver of modules,
features and flags; the build tools under test (CMake + Ninja, Meson +
Ninja) only read the result. The export contains, for every object file,
the compiler, the source, the object path and the exact flags, plus the
link command. Steps Make runs before compiling (package downloads,
generated headers such as riotbuild.h) are not exported: the build tools
reuse their results from the same tree.

The module list is taken from the `-DMODULE_<NAME>` arguments of the
genconfigheader call (RIOT passes them through the generated riotbuild.h,
not as compiler flags), the CPU from `-DRIOT_CPU=CPU_<NAME>`; runtime variables for flashing
and the terminal (group 2B) come from an optional JSON file with values of
`make info-debug-variable-<NAME>` (FLASHER, FFLAGS, TERMPROG, TERMFLAGS,
PORT, SIZE, ELFFILE).

Usage: export_resolved_state.py <make.log> <app> <board> [runtime.json]
       > resolved-state.json
"""

import json
import re
import shlex
import sys

DEP_FLAGS_WITH_ARG = {"-MQ", "-MT", "-MF"}
DEP_FLAGS = {"-MD", "-MP", "-MMD"}


def commands(log: str) -> list[str]:
    """Logical command lines: continuation lines (`\\`) joined."""
    out, cur = [], ""
    for line in log.splitlines():
        if cur:
            cur += " " + line.strip()
        else:
            cur = line.rstrip()
        if cur.endswith("\\"):
            cur = cur[:-1].rstrip()
            continue
        out.append(cur)
        cur = ""
    return out


# options whose value is the next argument
VALUE_OPTS = {"-o", "-include", "-imacros", "-isystem", "-x", "-MQ", "-MT",
              "-MF"}
SOURCE_RE = re.compile(r"\.(?:c|cc|cpp|cxx|s|S)$")


def parse_compile(argv: list[str]) -> dict | None:
    if "-c" not in argv:
        return None
    flags, sources, obj = [], [], None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in VALUE_OPTS and i + 1 < len(argv):
            if a == "-o":
                obj = argv[i + 1]
            elif a not in DEP_FLAGS_WITH_ARG:
                flags += [a, argv[i + 1]]
            i += 2
            continue
        if a in DEP_FLAGS or a == "-c":
            i += 1
            continue
        if not a.startswith("-") and SOURCE_RE.search(a):
            sources.append(a)
        else:
            flags.append(a)
        i += 1
    if len(sources) != 1 or obj is None:
        return None
    return {"compiler": argv[0], "source": sources[0], "object": obj,
            "flags": flags}


def main() -> int:
    log_path, app, board = sys.argv[1:4]
    log = open(log_path, errors="replace").read()
    objects, link, module_defs = [], None, set()
    for cmd in commands(log):
        if "genconfigheader" in cmd:
            module_defs |= set(re.findall(r"-DMODULE_([A-Z0-9_]+)", cmd))
        if not re.match(r"^\S*(?:gcc|g\+\+|clang)\s", cmd):
            continue
        if re.search(r"-o \S+/" + re.escape(app) + r"\.elf(\s|$)", cmd):
            # link: `$(find <dirs> -name "*.o" | sort)` is expanded by the
            # shell; the build tools pass their own object list instead
            m = re.match(r"^(\S+)\s+\$\(find .*?\| sort\)\s*(.*)$", cmd)
            if not m:
                print(f"error: unexpected link command: {cmd[:200]}",
                      file=sys.stderr)
                return 1
            link = {"linker": m.group(1), "flags": shlex.split(m.group(2))}
            continue
        try:
            argv = shlex.split(cmd)
        except ValueError:
            continue
        entry = parse_compile(argv)
        if entry:
            objects.append(entry)
    if link is None or not objects:
        print("error: no link command or no compile commands in the log",
              file=sys.stderr)
        return 1
    # drop `-o <elf>` from the link flags; the build tool sets the output
    flags = link["flags"]
    if "-o" in flags:
        k = flags.index("-o")
        link["output"] = flags[k + 1]
        del flags[k:k + 2]
    objects.sort(key=lambda e: e["object"])
    flags = {f for o in objects for f in o["flags"]}
    derived = sorted(m.lower() for m in module_defs)
    cpus = sorted(f.split("=CPU_", 1)[1].lower() for f in flags
                  if f.startswith("-DRIOT_CPU=CPU_"))
    state = {"schema": "riot-resolved-build/0", "application": app,
             "board": board, "cpu": cpus[0] if len(cpus) == 1 else None,
             "modules": derived, "objects": objects, "link": link}
    if len(sys.argv) > 4:
        rt = json.load(open(sys.argv[4]))
        # the resolver's own module list wins; the MODULE_* defines must be
        # exactly modules + packages (package names with '-' become '_')
        if "MODULES" in rt:
            state["modules"] = sorted(rt.pop("MODULES"))
            pkgs = {p.replace("-", "_") for p in rt.pop("PACKAGES", [])}
            expected = sorted(set(state["modules"]) | pkgs)
            state["module_defines_consistent"] = expected == derived
            if expected != derived:
                print("warning: MODULE_* defines differ from modules + "
                      f"packages: {sorted(set(expected) ^ set(derived))}",
                      file=sys.stderr)
        state["runtime"] = rt
    json.dump(state, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
