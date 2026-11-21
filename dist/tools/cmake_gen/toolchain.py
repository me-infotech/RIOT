# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Toolchain probes of the build (step G3-1).

RIOT's Make files ask the toolchain a few questions with `$(shell …)`. The
build data reads the answers as PROBE_* variables; each provider below runs
the same command as the Make file (without a shell; the result is the same:
an exit status, a version, a path), with the values of the data (CC, LINK,
PREFIX, …). A missing toolchain gives the answers Make gets without it
(exit status 127, empty version, link tests fail), so the command lines can
be compared with `make -n` on a host without the toolchain.

  PROBE_GCC_VERSION        gnu.inc.mk:33       major version of `CC -dumpversion`
  PROBE_CC_STD_C11         cflags.inc.mk:3     exit status of `CC -std=c11 -E -`
  PROBE_CC_STD_CXX14       cflags.inc.mk:37    exit status of `CC -std=c++14 -E -`
  PROBE_LINK_NOEXECSTACK   cflags.inc.mk:58    1/0: link test with `-z noexecstack`
  PROBE_LINK_NOWARNRWX     Makefile.include:414 1/0: link test, --no-warn-rwx-segments
  PROBE_LINK_NANO_SPECS    libc/newlib.mk:5    exit status of `LINK -specs=nano.specs -E -`
  PROBE_LINK_NANO_WCHAR_WARNING newlib.mk:7    0 if a nano link warns about wchar_t
  PROBE_NEWLIB_INCLUDE_DIR newlib.mk:30-55     directory of newlib.h
  PROBE_NEWLIB_NANO_INCLUDE_DIR newlib.mk:66   nano include directory
  PROBE_OBJCOPY            gnu.inc.mk:22       first of PREFIX-objcopy, gobjcopy, objcopy
  PROBE_OBJDUMP            gnu.inc.mk:30       first of PREFIX-objdump, gobjdump; objdump
  PROBE_GIT_DESCRIBE       git_version.inc.mk:2 `git --git-dir=RIOTBASE/.git describe …`
  PROBE_GIT_BRANCH         git_version.inc.mk:3 `git … rev-parse --abbrev-ref HEAD`
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess

# The only module of the build that starts processes at generation time: the
# probes ask the compiler and git, never make.
C_ENV = {"LC_ALL": "C"}


def _run(argv: list, stdin: str = "", merge: bool = False):
    """(exit status, stdout[+stderr]); 127 if the program does not exist."""
    if not argv or shutil.which(argv[0]) is None:
        return 127, ""
    env = dict(os.environ, **C_ENV)
    try:
        res = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                             env=env, check=False)
    except OSError:
        return 127, ""
    return res.returncode, res.stdout + (res.stderr if merge else "")


def _minimal(v) -> str:
    return os.path.join(v.get("RIOTTOOLS"), "testprogs", "minimal_linkable.c")


def gcc_version(v) -> str:
    status, out = _run(v.get("CC").split() + ["-dumpversion"])
    if status != 0 or not out.split():
        return ""
    return out.split()[0].split(".")[0]


def cc_std(flag: str):
    def probe(v) -> str:
        return str(_run(v.get("CC").split() + [flag, "-E", "-"])[0])
    return probe


def link_test(*extra: str):
    def probe(v) -> str:
        argv = v.get("LINK").split() + [_minimal(v), "-o", "/dev/null", "-lc", "-Wall",
                                         "-Wextra", "-pedantic", *extra]
        return "1" if _run(argv)[0] == 0 else "0"
    return probe


def nano_specs(v) -> str:
    return str(_run(v.get("LINK").split() + ["-specs=nano.specs", "-E", "-"])[0])


def nano_wchar_warning(v) -> str:
    status, out = _run(v.get("LINK").split() + [_minimal(v), "-o", "/dev/null", "-lc",
                                               "-specs=nano.specs", "-Wall", "-Wextra",
                                               "-pedantic"], merge=True)
    if status == 127:
        return "1"
    return "0" if "use of wchar_t values across objects may fail" in out else "1"


def compiler_include_paths(v) -> list:
    """newlib.mk:31-36: the `#include <...>` search list of PREFIX-gcc."""
    status, out = _run([v.get("PREFIX") + "gcc", "-v", "-x", "c", "-E", "/dev/null"], merge=True)
    if status == 127:
        return []
    lines = out.split("\n")
    try:
        start = lines.index("#include <...> search starts here:") + 1
        end = lines.index("End of search list.", start)
    except ValueError:
        return []
    return [line.strip() for line in lines[start:end]]


def newlib_include_dir(v) -> str:
    """newlib.mk:30-55: the first directory with newlib.h of the compiler's
    search list, else of the known install locations, else next to the
    compiler."""
    arch = v.get("TARGET_ARCH")
    for path in compiler_include_paths(v):
        if os.path.exists(os.path.join(path, "newlib.h")):
            return os.path.realpath(path)
    patterns = [f"/etc/alternatives/gcc-{arch}-include", f"/usr/{arch}/include",
                f"/usr/local/opt/{arch}*/{arch}/include", f"/usr/local/opt/gcc-*/{arch}/include"]
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.join(pattern, "newlib.h"))):
            return os.path.realpath(os.path.dirname(path))
    gcc = shutil.which(v.get("PREFIX") + "gcc")
    if gcc:
        candidate = os.path.join(os.path.dirname(gcc), "..", arch, "include")
        if os.path.exists(candidate):
            return os.path.realpath(candidate)
    return ""


def newlib_nano_include_dir(v) -> str:
    base = v.get("NEWLIB_INCLUDE_DIR")
    if not base:
        return ""
    for sub in ("newlib-nano", "newlib/nano", "nano"):
        if os.path.exists(os.path.join(base, sub)):
            return os.path.join(base, sub)
    return ""


def first_command(*names: str):
    def probe(v) -> str:
        for name in names:
            name = name.replace("{PREFIX}", v.get("PREFIX"))
            path = shutil.which(name)
            if path:
                return path
        return ""
    return probe


def objdump(v) -> str:
    return first_command("{PREFIX}objdump", "gobjdump")(v) or "objdump"


def git(*args: str):
    def probe(v) -> str:
        git_dir = os.path.join(v.get("RIOTBASE"), ".git")
        status, out = _run(["git", f"--git-dir={git_dir}", *args])
        return out.strip() if status == 0 else ""
    return probe


PROVIDERS = {
    "PROBE_GCC_VERSION": gcc_version,
    "PROBE_CC_STD_C11": cc_std("-std=c11"),
    "PROBE_CC_STD_CXX14": cc_std("-std=c++14"),
    "PROBE_LINK_NOEXECSTACK": link_test("-z", "noexecstack"),
    "PROBE_LINK_NOWARNRWX": link_test("-Wl,--no-warn-rwx-segments"),
    "PROBE_LINK_NANO_SPECS": nano_specs,
    "PROBE_LINK_NANO_WCHAR_WARNING": nano_wchar_warning,
    "PROBE_NEWLIB_INCLUDE_DIR": newlib_include_dir,
    "PROBE_NEWLIB_NANO_INCLUDE_DIR": newlib_nano_include_dir,
    "PROBE_OBJCOPY": first_command("{PREFIX}objcopy", "gobjcopy", "objcopy"),
    "PROBE_OBJDUMP": objdump,
    "PROBE_GIT_DESCRIBE": git("describe", "--always", "--abbrev=4"),
    "PROBE_GIT_BRANCH": git("rev-parse", "--abbrev-ref", "HEAD"),
}
