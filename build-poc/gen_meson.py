#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Write a Meson project (meson.build + cross file) that builds the
application described by a resolved-state.json (export_resolved_state.py).

Meson has no per-source compile flags: sources with the same flag set go
into one static library (c_args), and the executable takes the objects one
by one (extract_objects) in the order of Make's object paths, which is the
link order of `$(find … -name "*.o" | sort)`.

Usage: gen_meson.py <resolved-state.json> <output dir>
"""

import json
import os
import shlex
import sys


def q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def lst(words: list[str]) -> str:
    return "[" + ", ".join(q(w) for w in words) + "]"


def run_targets(state: dict, app: str) -> list[str]:
    """Examples of groups 2A, 2B and 3 (D24) as Meson run targets. 2A and
    2B targets do not depend on the build: the ELF is passed as a path
    string (a target object would make Meson build it first); `flash`
    passes the target object and therefore builds first (group 3)."""
    lines = ["", "# group 2A: resolved state, printed without building",
             "run_target('info-modules', command: ['cat', "
             "meson.current_source_dir() / 'modules.txt'])",
             "run_target('info-cpu', command: "
             + lst(["echo", state["cpu"] or ""]) + ")"]
    rt = state.get("runtime")
    if not rt:
        return lines
    make_elf = rt["ELFFILE"]
    elf_path = "@ELF@"

    def runtime(name: str) -> list[str]:
        return [w.replace(make_elf, elf_path) for w in shlex.split(rt[name])]

    def expr(words: list[str], elf: str) -> str:
        parts = []
        for w in words:
            if w == elf_path:
                parts.append(elf)
            else:
                parts.append(q(w))
        return "[" + ", ".join(parts) + "]"
    path = f"meson.current_build_dir() / {q(app + '.elf')}"
    flash = [rt["FLASHER"]] + runtime("FFLAGS")
    lines += ["", "# group 2B: existing ELF / programmer / terminal, no build",
              "run_target('info-buildsize', command: "
              + expr(shlex.split(rt["SIZE"]) + ["-d", "-B", elf_path], path)
              + ")",
              "run_target('flash-only', command: " + expr(flash, path) + ")",
              "run_target('term', command: "
              + lst([rt["TERMPROG"]] + shlex.split(rt["TERMFLAGS"])) + ")",
              "", "# group 3: build, then flash",
              "run_target('flash', command: " + expr(flash, "elf") + ")"]
    return lines


def main() -> int:
    state = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    compilers = {o["compiler"] for o in state["objects"]}
    if len(compilers) != 1:
        print(f"error: more than one compiler: {compilers}", file=sys.stderr)
        return 1
    cc = compilers.pop()
    prefix = cc[:-len("gcc")] if cc.endswith("gcc") else ""
    with open(os.path.join(out, "cross.ini"), "w") as f:
        f.write(f"""[binaries]
c = {q(cc)}
ar = {q(prefix + 'ar')}
strip = {q(prefix + 'strip')}

[host_machine]
system = 'none'
cpu_family = 'arm'
cpu = 'cortex-m4'
endian = 'little'

[properties]
needs_exe_wrapper = true
""")
    app = state["application"]
    groups: dict[tuple, list] = {}
    for o in state["objects"]:
        groups.setdefault(tuple(o["flags"]), []).append(o["source"])
    lines = [f"project({q(app)}, 'c', meson_version: '>=1.3')", ""]
    lib_of = {}
    for i, (flags, sources) in enumerate(groups.items()):
        lines.append(f"objs{i} = static_library('objs{i}',")
        lines += [f"  {q(s)}," for s in sources]
        lines.append("  c_args: [" + ", ".join(q(f) for f in flags) + "],")
        lines.append("  build_by_default: false)")
        for s in sources:
            lib_of[s] = i
    lines.append("")
    lines.append(f"elf = executable({q(app + '.elf')},")
    lines.append("  objects: [")
    for o in state["objects"]:
        lines.append(f"    objs{lib_of[o['source']]}.extract_objects("
                     f"{q(o['source'])}),")
    lines.append("  ],")
    lines.append("  link_args: [" + ", ".join(
        q(f) for f in state["link"]["flags"]) + "])")
    with open(os.path.join(out, "modules.txt"), "w") as f:
        f.write("".join(m + "\n" for m in state["modules"]))
    lines += run_targets(state, app)
    with open(os.path.join(out, "meson.build"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
