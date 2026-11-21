# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Comparison of build command lines: GNU Make's `make -n -k` output against
the commands of the build without Make (the plan, or `ninja -t commands`).

Both sides are normalised the same way:
  * paths: the repository, the build directory of the packages (BUILD_DIR)
    and the directory of the objects (BINDIR) become @RIOTBASE@,
    @BUILD_DIR@, @BINDIR@;
  * the RIOT version (from `git describe`, it names the checkout) is masked;
  * a command is compared as its argument vector (shell words): Make prints
    recipe lines with `\\` continuations and blanks of empty variables;
  * the link: Make lists the objects at run time with
    `$(find <module dirs> -name "*.o" | sort)`; the comparison expands this
    to the objects of Make's own compile commands in those directories,
    sorted - what `find | sort` gives after the compile step (C locale).
"""

from __future__ import annotations

import re
import shlex

VERSION_RE = re.compile(r"(-DRIOT_VERSION=\\?\"?)[^ ]*?(\\?\"?(?= |$))")
FIND_RE = re.compile(r"\$\(find (.*?) -name \"\*\.o\" 2> /dev/null \| sort\)")


def normalise_paths(text: str, mapping: dict) -> str:
    for path, name in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(path, name)
    return text


def mask_version(text: str) -> str:
    text = re.sub(r"-DRIOT_VERSION=\\\"[^ ]*?\\\"(?= )", r'-DRIOT_VERSION=\\"@VERSION@\\"', text)
    text = re.sub(r"-DRIOT_VERSION=\\\"'UNKNOWN \(builddir: [^)]*\)'\\\"",
                  r'-DRIOT_VERSION=\\"@VERSION@\\"', text)
    return re.sub(r"RIOT_VERSION_NUM\\\(\d+,\d+,\d+,\d+\\\)", r"RIOT_VERSION_NUM\\(@CODE@\\)",
                  text)


def join_lines(text: str) -> list:
    """Make's recipe lines with their `\\` continuations joined."""
    out, cur = [], ""
    for line in text.split("\n"):
        if line.startswith("\t"):
            line = line[1:]
        if line.endswith("\\"):
            cur += line[:-1] + " "
            continue
        out.append(cur + line)
        cur = ""
    if cur:
        out.append(cur)
    return out


def classify(lines: list, cc: str, link: str) -> dict:
    """The build commands of a list of shell lines, by kind:
    compile (by object), link, objcopy, size, riotbuild, pp_header."""
    out = {"compile": {}, "link": None, "objcopy": None, "size": None,
           "riotbuild": None, "riotbuild_sed": None, "pp_header": None}
    for line in lines:
        words = line.split()
        if not words:
            continue
        if words[0] == cc and " -c " in line:
            argv = shlex.split(line)
            out["compile"][argv[argv.index("-o") + 1]] = argv
        elif words[0] == link and ("$(find" in line or " -o " in line) and " -c " not in line:
            out["link"] = line
        elif "-Obinary" in words:
            out["objcopy"] = shlex.split(line)
        elif words[0].endswith("size") and len(words) == 2 and words[1].endswith(".elf"):
            out["size"] = shlex.split(line)
        elif "genconfigheader.sh" in line:
            out["riotbuild"] = line
        elif line.startswith("sed -n -e '1i"):
            out["riotbuild_sed"] = line
        elif "generate_pp_successor_header.sh" in line:
            out["pp_header"] = line
    return out


def expand_find(link_line: str, objects: list) -> list:
    """argv of Make's link line with `$(find …| sort)` replaced (see above)."""
    match = FIND_RE.search(link_line)
    if not match:
        return shlex.split(link_line)
    dirs = match.group(1).split()
    found = sorted(o for o in objects if any(o.startswith(d) for d in dirs))
    return shlex.split(link_line[:match.start()]) + found + \
        shlex.split(link_line[match.end():])


def make_commands(text: str, mapping: dict, cc: str, link: str) -> dict:
    """Commands of `make -n -k` output (normalised)."""
    lines = join_lines(mask_version(normalise_paths(text, mapping)))
    cmds = classify(lines, cc, link)
    if cmds["link"] is not None:
        cmds["link"] = expand_find(cmds["link"], list(cmds["compile"]))
    return cmds


def header_args(line: str) -> list:
    """The words of the genconfigheader command (before the pipe) and of the
    lazysponge command (after it), without the `mkdir -p … &&` of the plan."""
    if line is None:
        return None
    line = line.split("&&", 1)[1] if line.startswith("mkdir -p") else line
    left, right = line.split("|", 1)
    return [shlex.split(left), shlex.split(right)]


def pp_args(line: str):
    if line is None:
        return None
    line = line.split("&&", 1)[1] if line.startswith("mkdir -p") else line
    return shlex.split(line)


def plan_commands(plan: dict, mapping: dict) -> dict:
    """The same kinds of commands from a build plan (normalised)."""
    lines = [o["command"] for m in plan["modules"] for o in m["objects"]]
    lines += [plan["link"]["command"]] + [f["command"] for f in plan["files"]]
    lines += [plan["size"]] + [h["command"] for h in plan["headers"]]
    lines = [mask_version(normalise_paths(line, mapping)) for line in lines]
    cmds = classify(lines, plan["tools"]["CC"], plan["tools"]["LINK"])
    if cmds["link"] is not None:
        cmds["link"] = shlex.split(cmds["link"])
    return cmds


def compare(make: dict, other: dict) -> list:
    """Differences (empty: the same commands)."""
    problems = []
    only_make = sorted(set(make["compile"]) - set(other["compile"]))
    only_other = sorted(set(other["compile"]) - set(make["compile"]))
    if only_make:
        problems.append(f"objects only in Make: {only_make}")
    if only_other:
        problems.append(f"objects only without Make: {only_other}")
    for obj in sorted(set(make["compile"]) & set(other["compile"])):
        if make["compile"][obj] != other["compile"][obj]:
            a, b = make["compile"][obj], other["compile"][obj]
            problems.append(f"compile {obj}: Make {[w for w in a if w not in b]} "
                            f"vs {[w for w in b if w not in a]} (or order)")
    for kind in ("link", "objcopy", "size"):
        if make[kind] != other[kind]:
            problems.append(f"{kind}: {make[kind]} != {other[kind]}")
    if header_args(make["riotbuild"]) != header_args(other["riotbuild"]):
        problems.append("riotbuild.h command differs")
    if pp_args(make["pp_header"]) != pp_args(other["pp_header"]):
        problems.append("preprocessor_successor.h command differs")
    return problems
