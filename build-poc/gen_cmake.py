#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Write a CMake project (CMakeLists.txt + toolchain file) that builds the
application described by a resolved-state.json (export_resolved_state.py).

Every source keeps its exact compile flags (source property COMPILE_OPTIONS);
sources are listed in the order of Make's object paths, which is the link
order of `$(find … -name "*.o" | sort)`; the link rule is replaced so that
the command has Make's shape: objects first, then the link flags.

Usage: gen_cmake.py <resolved-state.json> <output dir>
"""

import json
import os
import shlex
import sys


def cmake_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace(
        "$", "\\$").replace(";", "\\;") + '"'


ELF_TOKEN = "@ELF@"


def cmd(words: list[str]) -> str:
    """Quoted CMake arguments; the ELF placeholder becomes the target file
    (a generator expression, which must not be escaped)."""
    return " ".join("$<TARGET_FILE:" + ELF_APP + ">" if w == ELF_TOKEN
                    else cmake_quote(w) for w in words)


ELF_APP = ""


def custom_targets(state: dict, app: str) -> list[str]:
    """Examples of groups 2A, 2B and 3 (D24) as CMake custom targets. 2A
    and 2B targets do not depend on the build (they read the resolved
    state or an existing ELF); `flash` builds first (group 3)."""
    global ELF_APP
    ELF_APP = app + ".elf"
    elf = ELF_TOKEN
    lines = [
        "# group 2A: resolved state, printed without building",
        "add_custom_target(info-modules COMMAND cat "
        "${CMAKE_CURRENT_SOURCE_DIR}/modules.txt VERBATIM)",
        "add_custom_target(info-cpu COMMAND echo "
        + cmd([state["cpu"] or ""]) + " VERBATIM)",
    ]
    rt = state.get("runtime")
    if not rt:
        return lines
    make_elf = rt["ELFFILE"]

    def runtime(name: str) -> list[str]:
        return [w.replace(make_elf, elf) for w in shlex.split(rt[name])]
    flash = [rt["FLASHER"]] + runtime("FFLAGS")
    lines += [
        "# group 2B: existing ELF / programmer / terminal, no build",
        "add_custom_target(info-buildsize COMMAND "
        + cmd(shlex.split(rt["SIZE"]) + ["-d", "-B", elf]) + " VERBATIM)",
        "add_custom_target(flash-only COMMAND " + cmd(flash)
        + " USES_TERMINAL VERBATIM)",
        "add_custom_target(term COMMAND "
        + cmd([rt["TERMPROG"]] + shlex.split(rt["TERMFLAGS"]))
        + " USES_TERMINAL VERBATIM)",
        "# group 3: build, then flash",
        f"add_custom_target(flash COMMAND {cmd(flash)} DEPENDS {app}.elf "
        "USES_TERMINAL VERBATIM)",
    ]
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
    with open(os.path.join(out, "toolchain.cmake"), "w") as f:
        f.write(f"""set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER {cc})
# the compiler check must not link: there is no C runtime for the target
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
""")
    app = state["application"]
    lines = [
        "cmake_minimum_required(VERSION 3.20)",
        f"project({app} LANGUAGES C)",
        "# no flags of CMake's own: every flag comes from the resolved state",
        'set(CMAKE_C_FLAGS "")',
        'set(CMAKE_BUILD_TYPE "")',
        'set(CMAKE_C_FLAGS_INIT "")',
        "# Make's link shape: objects first, then the link flags",
        'set(CMAKE_C_LINK_EXECUTABLE '
        '"<CMAKE_C_COMPILER> <OBJECTS> <LINK_FLAGS> -o <TARGET>")',
        "set(SOURCES",
    ]
    for o in state["objects"]:
        lines.append(f"    {o['source']}")
    lines.append(")")
    lines.append(f"add_executable({app}.elf ${{SOURCES}})")
    for o in state["objects"]:
        opts = ";".join(cmake_quote(f)[1:-1] for f in o["flags"])
        lines.append(f'set_source_files_properties({o["source"]} PROPERTIES '
                     f'COMPILE_OPTIONS "{opts}")')
    link = " ".join(state["link"]["flags"])
    lines.append(f'set_target_properties({app}.elf PROPERTIES LINK_FLAGS '
                 f'{cmake_quote(link)})')
    with open(os.path.join(out, "modules.txt"), "w") as f:
        f.write("".join(m + "\n" for m in state["modules"]))
    lines += custom_targets(state, app)
    with open(os.path.join(out, "CMakeLists.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
