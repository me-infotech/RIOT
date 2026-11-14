#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Compare the compile flags of a build tool (compile_commands.json) with
the flags of the resolved state, per source file: missing flags, extra
flags (added by the tool) and whether the resolved flags keep their order.

Usage: compare_flags.py <resolved-state.json> <compile_commands.json> <name>
"""

import collections
import json
import shlex
import sys

SKIP_WITH_ARG = {"-o", "-MF", "-MQ", "-MT"}
SKIP = {"-c", "-MD", "-MP", "-MMD"}


def main() -> int:
    state = {o["source"]: o for o in json.load(open(sys.argv[1]))["objects"]}
    entries = json.load(open(sys.argv[2]))
    name = sys.argv[3]
    extra, missing = collections.Counter(), collections.Counter()
    files = in_order = 0
    for e in entries:
        src = e["file"]
        if src not in state:
            continue
        files += 1
        args = e.get("arguments") or shlex.split(e["command"])
        have, i = [], 1
        while i < len(args):
            a = args[i]
            if a in SKIP_WITH_ARG:
                i += 2
                continue
            if a not in SKIP and a != src:
                have.append(a)
            i += 1
        want = state[src]["flags"]
        extra.update(set(have) - set(want))
        missing.update(set(want) - set(have))
        in_order += [a for a in have if a in want] == \
            [a for a in want if a in have]
    print(f"{name}: {files}/{len(state)} sources; flags missing: "
          f"{dict(missing) or 'none'}; extra flags: {dict(extra) or 'none'}; "
          f"resolved flags in the same order: {in_order}/{files}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
