# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""The algorithm of the build system: what Make's pipeline files do with
the configuration data, implemented in Python.

Each function names the Make file and lines it replaces (base commit
827338cf72). The configuration itself (dependency rules, provided
features, default modules, stdio backends, features -> modules) is data
and evaluated with evaluate.Evaluator; only the order of evaluation, the
fixpoint, the features check and the checks of the result are code.
"""

from __future__ import annotations

import os
import sys

from evaluate import OutOfScope, ResolveError, RIOTBASE, rel
from variables import drop, keep, sort

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features_yaml2mx"))

# pylint: disable=wrong-import-position
import yaml  # noqa: E402

MAX_PASSES = 50           # the fixpoint is reached after 3-4 passes in the scope
BOARD_ALIASES = ("native", "feather-nrf52840", "feather-nrf52840-sense")


def data(path: str) -> str:
    """Absolute path of the YAML next to a Make file of the repository."""
    return os.path.join(RIOTBASE, path)


# --- makefiles/features_check.inc.mk -----------------------------------------------
def features_check(v):
    """makefiles/features_check.inc.mk:1-93 (all lines)."""
    # :5-7 required for every build; FEATURES_REQUIRED stays recursive, so
    # the selection is evaluated whenever the variable is used (like Make)
    for prefix in ("arch_%", "bug_%", "cpu_%"):
        v.add("FEATURES_REQUIRED", {"select": {"var": "FEATURES_PROVIDED", "match": [prefix]}})
    required = v.words("FEATURES_REQUIRED")
    provided = v.words("FEATURES_PROVIDED")
    blacklist = v.words("FEATURES_BLACKLIST")
    conflicts = [c.split(":") for c in v.words("FEATURES_CONFLICT")]
    # :10 (FEATURES_OPTIONAL_USED of the previous pass, empty in the first)
    used_so_far = sort(required + v.words("FEATURES_OPTIONAL_USED"))
    # :16-22 features that would conflict with a used one
    would_conflict = []
    for group in conflicts:
        if keep(used_so_far, group):
            would_conflict += drop(used_so_far, group)
    v.set_words("FEATURES_WOULD_CONFLICT", would_conflict)
    # :25-26
    usable = drop(blacklist + would_conflict, provided)
    v.set_words("FEATURES_USABLE", usable)
    # :29-35
    optional_only = sort(drop(required, v.words("FEATURES_OPTIONAL")))
    optional_used = sort(keep(usable, optional_only))
    v.set_words("FEATURES_OPTIONAL_ONLY", optional_only)
    v.set_words("FEATURES_OPTIONAL_USED", optional_used)
    v.set_words("FEATURES_OPTIONAL_MISSING", sort(drop(usable, optional_only)))
    # :38
    used_so_far = sort(required + optional_used)
    v.set_words("FEATURES_USED_SO_FAR", used_so_far)
    # :59-64 one out of each `a|b|c`: a used one, else a usable one, else the first
    one_out_of = []
    for item in v.words("FEATURES_REQUIRED_ANY"):
        alternatives = item.split("|")
        one_out_of.append((keep(used_so_far, alternatives) + keep(usable, alternatives)
                           + alternatives)[0])
    v.set_words("FEATURES_REQUIRED_ONE_OUT_OF", one_out_of)
    # :68-70, :73-75
    v.set_words("FEATURES_MISSING", sort(drop(provided, required + one_out_of)))
    used = sort(required + one_out_of + optional_used)
    v.set_words("FEATURES_USED", used)
    # :78-89 groups whose features are all used
    conflicting = []
    for group in conflicts:
        if len(keep(used, group)) == len(group):
            conflicting += group
    v.set_words("FEATURES_CONFLICTING", sort(conflicting))
    # :93
    v.set_words("FEATURES_USED_BLACKLISTED", sort(keep(used, blacklist)))


# --- makefiles/dependency_resolution.inc.mk --------------------------------------
def paths_with_makefile(dirs: list, names: list) -> list:
    """`$(sort $(foreach dir,…,$(foreach x,…,$(dir $(wildcard $(dir)/$(x)/Makefile)))))`:
    the directories of the names that have a build file (only tested for
    existence, never read)."""
    return sort(os.path.join(d, n) + "/" for d in dirs for n in names
                if os.path.isfile(os.path.join(d, n, "Makefile")))


def state(v) -> tuple:
    return (v.get("USEMODULE"), v.get("USEPKG"), v.get("FEATURES_USED"))


def dependency_pass(ev):
    """makefiles/dependency_resolution.inc.mk:5-35: one pass."""
    v = ev.v
    v.set_words("EXTERNAL_MODULE_PATHS",
                paths_with_makefile(v.words("EXTERNAL_MODULE_DIRS"), v.words("USEMODULE")))
    v.set_words("PKGDIRS", v.words("RIOTPKG") + v.words("EXTERNAL_PKG_DIRS"))
    v.set_words("PKG_PATHS", paths_with_makefile(v.words("PKGDIRS"), v.words("USEPKG")))
    old = state(v)
    ev.include_one(os.path.join(v.get("RIOTBASE"), "Makefile.dep"), False, "pipeline")  # :18
    ev.include_one(os.path.join(v.get("RIOTBOARD"), "Makefile.features"), False,
                   "pipeline")                                                          # :22
    features_check(v)                                                                   # :25
    ev.run_file(data("makefiles/features_modules.inc.yaml"))                           # :28
    for name in ("USEMODULE", "USEPKG", "FEATURES_USED"):                              # :31-33
        v.set_words(name, sort(v.words(name)))
    return old != state(v)                                                              # :39


def features_existing() -> list:
    """FEATURES_EXISTING (makefiles/features_existing.inc.mk is generated
    from features.yaml, its source)."""
    from features_yaml2mx import collect_features  # pylint: disable=import-outside-toplevel
    with open(os.path.join(RIOTBASE, "features.yaml"), encoding="utf-8") as file:
        return collect_features(yaml.safe_load(file))


def resolve_dependencies(ev, info_goal: bool = True) -> int:
    """makefiles/dependency_resolution.inc.mk:1-140: the fixpoint and the
    finalisation. Returns the number of passes."""
    v = ev.v
    passes = 1
    while dependency_pass(ev):                                                          # :39-40
        passes += 1
        if passes > MAX_PASSES:
            raise ResolveError(f"no fixpoint after {MAX_PASSES} passes")
    ev.run_file(data("makefiles/defaultmodules_no_recursive_deps.inc.yaml"))            # :42
    disable = v.words("DISABLE_MODULE")
    for module in drop(disable, ["auto_init", "periph_init"]):                         # :46
        v.add("USEMODULE", module)
    for module in ("auto_init", "periph_init"):                                        # :48-54
        if module not in v.words("USEMODULE"):
            v.add("DISABLE_MODULE", f"{module}_%")
    for module in drop(v.words("DISABLE_MODULE"), v.words("DEFAULT_MODULE")):          # :58
        v.add("USEMODULE", module)
    ev.run_file(data("makefiles/defaultmodules_deps.inc.yaml"))                        # :61
    v.set_words("USEMODULE", sort(v.words("USEMODULE")))                               # :64
    v.set_words("DEFAULT_MODULE", sort(v.words("DEFAULT_MODULE")))                     # :65
    ev.run_file(data("makefiles/deprecated_modules.inc.yaml"))                         # :68
    deprecated = sort(keep(v.words("DEPRECATED_MODULES"), v.words("USEMODULE")))       # :69-73
    v.set_words("DEPRECATED_MODULES_USED", deprecated)
    if deprecated:
        ev.messages.append(("info", "Deprecated modules are in use: " + " ".join(deprecated)))
    existing = features_existing()                                                     # :76-95
    for var, text in (("FEATURES_PROVIDED", f"provided by the board {v.get('BOARD')}"),
                      ("FEATURES_REQUIRED", "listed in FEATURES_REQUIRED"),
                      ("FEATURES_REQUIRED_ANY", "listed in FEATURES_REQUIRED_ANY"),
                      ("FEATURES_OPTIONAL", "listed in FEATURES_OPTIONAL")):
        words = [w for x in v.words(var) for w in x.split("|")]
        unknown = sort(drop(existing, words))
        if unknown:
            raise ResolveError(f"The following non-existing features are {text}: "
                               + " ".join(unknown))
    if not info_goal:                                                                  # :97-140
        insecure_checks(ev)
    return passes


def insecure_checks(ev):
    """makefiles/dependency_resolution.inc.mk:97-140 (not for info-% goals)."""
    v = ev.v
    for module, flag, text in (
            ("auto_init_telnet", "I_UNDERSTAND_THAT_TELNET_IS_INSECURE",
             "Telnet will be started automatically"),
            ("stdio_udp", "I_UNDERSTAND_THAT_STDIO_UDP_IS_INSECURE",
             "stdio via UDP will be started automatically")):
        if module in v.words("USEMODULE"):
            if v.get(flag).strip() != "1":
                raise ResolveError(f"{flag} must be set to 1 to proceed.")
            ev.messages.append(("warning", f"{text}, don't run this on public networks!"))
    if "psa_crypto" in v.words("USEMODULE"):
        ev.messages.append(("warning", "You are going to use the PSA Crypto module, which is "
                                       "only partly implemented and not yet thouroughly tested."))


# --- Makefile.include ----------------------------------------------------------------
def prelude(ev, board: bool = True):
    """Makefile.include:27-38 (directories), :53 (Makefile.local), :57-59,
    :74-75 (board aliases), :128-129 (OS), :153-171 (TOOLCHAIN), :173
    (cargo-settings.inc.mk:49-59), :193-202 (BOARDDIR)."""
    v = ev.v
    root = os.path.normpath(v.get("RIOTBASE") or RIOTBASE)
    if root != RIOTBASE:
        raise OutOfScope(f"RIOTBASE {root} is not the repository of the data ({RIOTBASE})")
    v.set_words("RIOTBASE", [RIOTBASE])
    for name, sub in (("RIOTCPU", "cpu"), ("RIOTBOARD", "boards"), ("RIOTMAKE", "makefiles"),
                      ("RIOTPKG", "pkg"), ("RIOTTOOLS", "dist/tools")):
        v.set(name, os.path.join(RIOTBASE, sub), "conditional")
        v.set_words(name, [os.path.normpath(v.get(name))])
    for name in ("RIOT_MAKEFILES_GLOBAL_PRE", "APPLICATION_RUST_MODULE"):
        if v.get(name).strip():
            raise OutOfScope(f"{name} is set; not covered by the data")
    for name in ("Makefile.local", "app.config", "app.config.test", "user.config"):
        if os.path.exists(os.path.join(ev.curdir, name)):
            raise OutOfScope(f"{rel(os.path.join(ev.curdir, name))} exists; "
                             "not covered by the data")
    sysname, machine = os.uname().sysname, os.uname().machine
    v.set("OS", sysname, "simple")
    v.set("OS_ARCH", machine, "simple")
    toolchain = v.get("TOOLCHAIN").strip()
    v.set_words("TOOLCHAIN", [{"clang": "llvm", "gcc": "gnu", "": "gnu"}.get(toolchain,
                                                                           toolchain)])
    if not board:
        return
    name = v.get("BOARD").strip()
    if name in BOARD_ALIASES:
        raise OutOfScope(f"BOARD={name} is an alias (makefiles/board_alias.inc.mk); "
                         "give the board itself")
    v.set_words("BOARD", [name])
    find_boarddir(v)


def find_boarddir(v):
    """Makefile.include:193-202: the first of EXTERNAL_BOARD_DIRS and
    RIOTBOARD that has a directory named BOARD."""
    board = v.get("BOARD").strip()
    dirs = v.words("EXTERNAL_BOARD_DIRS") + v.words("RIOTBOARD")
    v.set_words("BOARDSDIRS", dirs)
    found = [d for d in dirs if os.path.isdir(os.path.join(d, board))]
    if not board or not found:
        raise ResolveError(f"The specified board {board} does not exist.")
    v.set_words("BOARDDIR", [os.path.normpath(os.path.join(found[0], board))])


def application(ev, info_goal: bool = True) -> int:
    """Makefile.include from :333 to :993, the parts that resolve the
    configuration. Returns the number of dependency passes."""
    v = ev.v
    ev.include_one(os.path.join(RIOTBASE, "Makefile.features"), False, "pipeline")    # :333
    ev.run_file(data("makefiles/defaultmodules_regular.inc.yaml"))                     # :343
    features_check(v)                                                                  # :349
    for module in drop(v.words("DISABLE_MODULE"), v.words("DEFAULT_MODULE")):          # :352
        v.add("USEMODULE", module)
    v.set_words("USEMODULE", sort(v.words("USEMODULE")))                               # :355
    passes = resolve_dependencies(ev, info_goal)                                       # :358
    v.set("APPLICATION_MODULE", "application_${APPLICATION}", "conditional")           # :496
    # :532 makefiles/bindist.inc.mk:2 (modules of a binary distribution are
    # added after the dependency resolution, without their dependencies)
    for module in drop(v.words("APPLICATION_MODULE"), v.words("BIN_USEMODULE")):
        v.add("USEMODULE", module)
    expected_errors(ev)                                                                # :908-993
    return passes


def expected_errors(ev):
    """Makefile.include:908-993: problems of the result; an error unless
    CONTINUE_ON_EXPECTED_ERRORS=1 (the toolchain test, :970-984, needs the
    CPU's Makefile.include and is not part of the data: see README)."""
    v = ev.v
    problems = []
    disabled = keep(v.words("DISABLE_MODULE"), v.words("USEMODULE"))                   # :912-917
    if disabled:
        problems.append("Required modules were disabled using DISABLE_MODULE: "
                        + " ".join(sort(disabled)))
        v.set_words("USEMODULE", drop(v.words("DISABLE_MODULE"), v.words("USEMODULE")))
    for var, text in (("FEATURES_MISSING", "There are unsatisfied feature requirements:"),
                      ("FEATURES_USED_BLACKLISTED", "Some feature requirements are blacklisted:"),
                      ("FEATURES_CONFLICTING", "The following features conflict:")):
        if v.words(var):                                                               # :920-951
            problems.append(f"{text} {v.get(var)}")
            if var == "FEATURES_CONFLICTING" and v.get("FEATURES_CONFLICT_MSG").strip():
                problems.append("Rationale: " + v.get("FEATURES_CONFLICT_MSG").strip())
    for old, new in (("BOARD_WHITELIST", "BOARDS_SUPPORTED"),                          # :932-933
                     ("BOARD_BLACKLIST", "BOARDS_UNSUPPORTED")):
        for board in v.words(old):
            v.add(new, board)
    board = v.get("BOARD")
    supported = v.words("BOARDS_SUPPORTED")
    if supported and not keep(supported, [board]):                                     # :953-961
        problems.append(f"The selected BOARD={board} is not listed in BOARDS_SUPPORTED.")
    if keep(v.words("BOARDS_UNSUPPORTED"), [board]):                                   # :964-968
        problems.append(f"The selected BOARD={board} is listed in BOARDS_UNSUPPORTED.")
    for text in problems:
        ev.messages.append(("info", text))
    v.set_words("EXPECT_ERRORS", ["1"] if problems else [])
    if problems:                                                                       # :986-992
        if v.get("CONTINUE_ON_EXPECTED_ERRORS").strip() != "1":
            raise ResolveError("; ".join(problems) + " (You can let the build continue on "
                               "expected errors by setting CONTINUE_ON_EXPECTED_ERRORS=1 "
                               "to the command line.)")
        ev.messages.append(("error", "EXPECT ERRORS!"))


# --- makefiles/info-global.inc.mk: info-boards-supported ----------------------------
def board_supported(ev) -> bool:
    """makefiles/info-global.inc.mk:26-74 for one board (info-boards-collect):
    features check first; if no feature is missing, default modules and the
    full dependency resolution, then missing, blacklisted and conflicting
    features exclude the board."""
    v = ev.v
    ev.include_one(os.path.join(RIOTBASE, "Makefile.features"), False, "pipeline")    # :34
    features_check(v)                                                                  # :39
    if v.words("FEATURES_MISSING"):                                                    # :40-44
        return False
    ev.run_file(data("makefiles/defaultmodules_regular.inc.yaml"))                     # :47
    for module in drop(v.words("DISABLE_MODULE"), v.words("DEFAULT_MODULE")):          # :48
        v.add("USEMODULE", module)
    resolve_dependencies(ev)                                                           # :50
    return not any(v.words(name) for name in                                           # :52-74
                   ("FEATURES_MISSING", "FEATURES_USED_BLACKLISTED", "FEATURES_CONFLICTING"))


def candidate_boards(v, boards: list) -> list:
    """makefiles/info-global.inc.mk:14-15."""
    supported = v.words("BOARDS_SUPPORTED")
    boards = keep(supported or ["%"], boards)
    return drop(v.words("BOARDS_UNSUPPORTED"), boards)
