# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""The build plan of an application (step G3-1): every command that GNU
Make's target `all` runs, computed from data only.

Inputs: the resolved state of the resolver of G0-2 (modules, packages,
features, CPU), the build data (`build.yaml`, `*.build.yaml`), the module
data (`module.yaml`, the source of the generated module Makefiles), the
package data (`pkg.yaml`, `*.pkg.yaml`) and the toolchain probes. No Make
file is opened and make is never run.

What is data and what is algorithm: the data says what each Make file
contributes (flags, include paths, sources, directories, packages); the
algorithm below is the part of the build system that is code in Make as
well:

  algorithm (this file)            replaces (Make file:line, base 984ebddbbe)
  directories                      Makefile.include:67-77, setup_dirs.inc.mk:28-38
  build_system (order of the data) Makefile.include:209-1047 (the order of its
                                   includes is in build.yaml)
  extdefines, realmodules          makefiles/modules.inc.mk:1-22
  version_tuple                    makefiles/utils/strings.mk:105-107
  walk_module (Makefile.base)      Makefile.base:16-150 (DIRS recursion,
                                   SUBMODULES, automatic sources, objects,
                                   compile commands)
  exported                         `export` of the variables to sub-makes
                                   (list in makefiles/vars.build.yaml)
  packages                         Makefile.include:742-748 (pkg-prepare,
                                   pkg-build), cpu/nrf5x_common/Makefile.include:15
  link, binfile, print-size        Makefile.include:641-700
  riotbuild.h, preprocessor header Makefile.include:1026-1034,
                                   sys/preprocessor/Makefile.include:15-17
  module check                     Makefile.include:679-681, modules.inc.mk:20-22
"""

from __future__ import annotations

import os
import shlex

import buildeval
import toolchain
from buildeval import (OutOfScope, ResolveError, BuildEvaluator, BuildVariables,  # noqa: F401
                       rel, RIOTBASE)

# pylint: disable=wrong-import-position,wrong-import-order
import pipeline  # noqa: E402  (resolver)
import resolver  # noqa: E402
import rules as R  # noqa: E402
from variables import drop, keep, macro_name  # noqa: E402

PLAN_SCHEMA = 1
MAKEFILE_BASE = "Makefile.base"


class Plan(dict):
    """JSON-able build plan."""


# --- values of the build algorithm -----------------------------------------------
def version_tuple(version: str) -> str:
    """`version_tuple` of makefiles/utils/strings.mk: 'major,minor,patch' of
    the part before the first '-', leading zeros removed, a missing patch
    0; empty if major or minor is missing or a part is not a number."""
    head = version.split("-", 1)[0] if version else ""
    parts = head.split(".") if head else []
    if not parts or not all(p.isdigit() for p in parts):
        return ""
    parts = [str(int(p)) for p in parts][:3]
    parts += ["0"] * (3 - len(parts)) if len(parts) == 2 else []
    return ",".join(parts) if len(parts) == 3 else ""


def riot_version_tuple(v) -> str:
    """Makefile.include:490-492: the tuple of RIOT_VERSION, else of
    RIOT_DUMMY_VERSION."""
    return version_tuple(v.get("RIOT_VERSION").strip()) or \
        version_tuple(v.get("RIOT_DUMMY_VERSION").strip())


def all_modules(v) -> list:
    """modules.inc.mk:3: the modules and packages, sorted."""
    return sorted(set(v.words("USEMODULE") + v.words("USEPKG")))


def extdefines(v) -> str:
    """modules.inc.mk:5-6: -DMODULE_<NAME> of every module and package."""
    return " ".join(f"-DMODULE_{macro_name(m)}" for m in all_modules(v))


def realmodules(v) -> list:
    """modules.inc.mk:12-13: the modules that are not pseudomodules (or are
    listed in NO_PSEUDOMODULES), in the order of all_modules()."""
    mods = all_modules(v)
    return (drop(v.words("PSEUDOMODULES"), mods)
            + keep(v.words("NO_PSEUDOMODULES"), mods))


PROVIDERS = dict(toolchain.PROVIDERS)
PROVIDERS["BUILD_RIOT_VERSION_TUPLE"] = riot_version_tuple
PROVIDERS["BUILD_EXTDEFINES"] = extdefines


# --- the top level ------------------------------------------------------------------
def directories(v):
    """Makefile.include:67-77 and makefiles/setup_dirs.inc.mk:28-38."""
    v.set("BUILD_DIR", "${RIOTBASE}/build", "conditional")
    v.set("APPDIR", "${CURDIR}", "conditional")
    v.set("BINDIRBASE", "${APPDIR}/bin", "conditional")
    v.set("PKGDIRBASE", "${BUILD_DIR}/pkg", "conditional")
    v.set("BINDIR", "${BINDIRBASE}/${BOARD}", "conditional")
    for name in ("APPDIR", "BUILD_DIR", "BINDIRBASE", "BINDIR", "PKGDIRBASE"):
        path = os.path.normpath(os.path.join(v.get("CURDIR"), v.get(name).strip()))
        v.command_line(name, path)   # `override … := $(abspath …)`


def evaluate_application(app_dir: str, variables: dict):
    """Resolve and evaluate the build data of the application; returns the
    evaluator with the variables of Make's top level after parsing."""
    v = BuildVariables(PROVIDERS)
    for name, value in variables.items():
        v.command_line(name, value)
    curdir = os.path.abspath(app_dir)
    v.set("CURDIR", curdir, "simple")
    ev = BuildEvaluator(v, curdir)
    ev.hooks["makefiles/features_check.inc.mk"] = lambda: pipeline.features_check(v)

    def build_system():
        pipeline.prelude(ev)                       # resolver, G0-2
        pipeline.application(ev, info_goal=False)  # resolver, G0-2
        directories(v)
        ev.run_file(os.path.join(RIOTBASE, "makefiles", "pseudomodules.build.yaml"))
        ev.run_file(os.path.join(RIOTBASE, "build.yaml"))
    resolver._run_application(ev, build_system)   # pylint: disable=protected-access
    return ev


def exported(v, names: list) -> dict:
    """The exported variables (`names`: BUILD_EXPORTED of the top level,
    makefiles/vars.build.yaml), expanded: what a sub-make finds in its
    environment."""
    return {name: v.get(name) for name in names if v.defined(name)}


def command_line(v) -> dict:
    """Variables of Make's command line: passed to every sub-make."""
    return {name: v.get(name) for name in v.names() if v.origin(name) == "command line"}


def child(env: dict, cmdline: dict, curdir: str, extra: dict = None) -> BuildVariables:
    """The variables a sub-make starts with (`make -C curdir`)."""
    v = BuildVariables(PROVIDERS)
    for name, value in env.items():
        v.set(name, value, "simple")
    for name, value in (extra or {}).items():
        v.set(name, value, "simple")
    for name, value in cmdline.items():
        v.command_line(name, value)
    v.set("CURDIR", curdir, "simple")
    return v


# --- Makefile.base ------------------------------------------------------------------
def _wildcard(v, pattern: str) -> list:
    return v.files({"match": [pattern]})


def makefile_base(v, curdir: str) -> dict:
    """Makefile.base:16-150 at the point where a module Makefile includes it:
    the module name, its sources and objects, the compile commands and the
    sub-directories. Returns the module."""
    dirs = sorted(set(os.path.normpath(os.path.join(curdir, d)) for d in v.words("DIRS")))
    module = v.get("MODULE").strip() or os.path.basename(curdir)
    v.set("MODULE", module, "conditional")
    src = v.words("SRC")
    if v.get("SUBMODULES").strip() == "1":
        v.set("NO_AUTO_SRC", "1", "simple")
        base = v.get("BASE_MODULE").strip() or module
        wanted = [w[len(base) + 1:] + ".c" for w in v.words("USEMODULE")
                  if w.startswith(base + "_")]
        wanted = drop(v.words("SUBMODULES_NO_SRC"), wanted)
        src = sorted(set(src + [f for f in wanted
                                if os.path.exists(os.path.join(curdir, f))]))
    no_auto = v.get("NO_AUTO_SRC").strip()
    srcxxext = v.get("SRCXXEXT").strip() or "cpp"
    if not src and not no_auto:
        src = drop(v.words("SRC_NOLTO"), _wildcard(v, "*.c"))
    srcxx = v.words("SRCXX")
    if not srcxx and not no_auto:
        srcxx = drop(v.words("SRCXXEXCLUDE"), _wildcard(v, f"*.{srcxxext}"))
    asmsrc = v.words("ASMSRC")
    if not asmsrc and not no_auto:
        asmsrc = _wildcard(v, "*.s")
    assmsrc = v.words("ASSMSRC")
    if not assmsrc and not no_auto:
        assmsrc = _wildcard(v, "*.S")
    if srcxx and "cpp" not in v.words("USEMODULE"):
        raise ResolveError('Found C++ source, but feature "cpp" is not used. '
                           'Add "FEATURES_REQUIRED += cpp"')
    cflags = v.get("CFLAGS")
    if v.get("STATIC_ANALYSIS").strip() == "1" and \
            v.get("MODULE_SUPPORTS_STATIC_ANALYSIS").strip() == "1":
        cflags = f"{v.get('CFLAGS_STATIC_ANALYSIS')} {cflags}"
    if v.get("WRITE_SARIF").strip() == "1":
        raise OutOfScope("WRITE_SARIF=1 is outside the build data")
    if srcxx or asmsrc or assmsrc or v.words("GENSRC") or v.words("BLOBS"):
        raise OutOfScope(f"{rel(curdir)}: C++, assembler, generated sources and blobs "
                         "are outside the build of step G3-1")
    bindir = v.get("BINDIR").strip()
    objects = []
    nolto = v.words("SRC_NOLTO")
    for name, lto in [(s, False) for s in nolto] + [(s, True) for s in src]:
        obj = os.path.join(bindir, module, os.path.splitext(name)[0] + ".o")
        source = os.path.normpath(os.path.join(curdir, name))
        flags = cflags + (f" {v.get('LTOFLAGS')}" if lto else "")
        words = [v.get("CCACHE"), v.get("CC"), flags, v.get("RCFLAGS"), v.get("INCLUDES"),
                 f"-MQ '{obj}'", "-MD -MP -c -o", obj, source]
        objects.append({"source": source, "object": obj, "cwd": curdir,
                        "command": " ".join(w.strip() for w in words if w.strip())})
    return {"name": module, "dir": curdir, "dirs": dirs, "objects": objects}


def walk_module(env: dict, cmdline: dict, curdir: str, data_file: str, extra: dict,
                modules: list, read: list, names: list):
    """`make -C curdir [-f file]`: evaluate the module data, then its
    sub-directories (each a sub-make with this module's exported variables)."""
    v = child(env, cmdline, curdir, extra)
    ev = BuildEvaluator(v, curdir)
    found = []
    ev.hooks[MAKEFILE_BASE] = lambda: found.append(makefile_base(v, curdir))
    if not os.path.isfile(data_file):
        make_file = R.make_name(data_file) if R.is_yaml_name(data_file) else data_file
        if os.path.exists(make_file):
            raise OutOfScope(f"{rel(make_file)} is not converted to module data "
                             f"({rel(data_file)} is missing)")
        raise ResolveError(f"{rel(data_file)}: no such file")
    ev.run_file(data_file)
    read.extend(ev.read)
    if len(found) != 1:
        raise ResolveError(f"{rel(data_file)} does not include ${{RIOTBASE}}/Makefile.base")
    module = found[0]
    module["data"] = rel(data_file)
    modules.append(module)
    sub_env = {**env, **exported(v, names)}
    for directory in module["dirs"]:
        walk_module(sub_env, cmdline, directory,
                    os.path.join(directory, R.MODULE_DATA), {}, modules, read, names)


# --- packages -------------------------------------------------------------------------
def package(env: dict, cmdline: dict, make_file: str, curdir: str, read: list,
            names: list) -> tuple:
    """The package step of one package (pkg/pkg.mk recipes) and the variables
    its build runs with."""
    data = buildeval.pkg_yaml_name(make_file)
    if not os.path.isfile(data):
        raise OutOfScope(f"{rel(make_file)} is not converted to package data "
                         f"({rel(data)} is missing)")
    v = child(env, cmdline, curdir)
    ev = BuildEvaluator(v, curdir)
    ev.run_file(data)
    read.extend(ev.read)
    get = lambda name: v.get(name).strip()  # noqa: E731
    spec = {
        "name": get("PKG_NAME"), "url": get("PKG_URL"), "version": get("PKG_VERSION"),
        "license": get("PKG_LICENSE"), "source_dir": get("PKG_SOURCE_DIR"),
        "sparse_paths": v.words("PKG_SPARSE_PATHS"), "patches": v.words("PKG_PATCHES"),
        "git_quiet": get("GIT_QUIET"), "gitflags": get("GITFLAGS"),
        "gitamflags": get("GITAMFLAGS"), "ci": get("RIOT_CI_BUILD") == "1",
        "build_dir": get("BUILD_DIR"),
        "copy": {"from": get("PKG_COPY_FROM"), "to": get("PKG_COPY_TO"),
                 "files": v.words("PKG_COPY_FILES")} if get("PKG_COPY_FILES") else None,
        "data": sorted(set(ev.read)),
        "make_file": rel(make_file),
    }
    build = None
    if get("PKG_BUILD_MODULE_FILE"):
        build = {"dir": get("PKG_BUILD_MODULE_DIR"),
                 "data": R.module_yaml_name(get("PKG_BUILD_MODULE_FILE")),
                 "env": {**env, **exported(v, names)}}
    return spec, build


# --- the plan ---------------------------------------------------------------------------
def build_plan(app_dir: str, variables: dict, prepare=None) -> Plan:
    """The plan of `make all` for the application and board of `variables`.
    `prepare(spec)` is called for each package before its modules are
    evaluated (the package step: sources must exist, as for Make)."""
    ev = evaluate_application(app_dir, variables)
    v = ev.v
    names = v.words("BUILD_EXPORTED")
    env, cmdline = exported(v, names), command_line(v)
    read = list(ev.read)
    modules: list = []
    packages = []
    pkg_files = [os.path.join(p, "Makefile") for p in v.words("PKG_PATHS")]
    for make_file in v.words("BUILD_PACKAGES") + pkg_files:
        curdir = v.get("CURDIR") if make_file in v.words("BUILD_PACKAGES") else \
            os.path.dirname(make_file)
        spec, build = package(env, cmdline, make_file, curdir, read, names)
        packages.append((spec, build))
    # the application module (application.inc.mk, the sub-make of
    # Makefile.include:684-686 with DIRS and APPLICATION_* in its environment)
    extra = {"DIRS": v.get("DIRS"), "APPLICATION_SRC": v.get("SRC"),
             "APPLICATION_SRCXX": v.get("SRCXX"), "APPLICATION_ASMSRC": v.get("ASMSRC"),
             "APPLICATION_ASSMSRC": v.get("ASSMSRC"), "APPLICATION_BLOBS": v.get("BLOBS")}
    walk_module(env, cmdline, v.get("APPDIR"), os.path.join(RIOTBASE, "makefiles",
                                                            "application.inc.yaml"),
                extra, modules, read, names)
    for spec, build in packages:
        if prepare is not None:
            prepare(spec)
        if build:
            walk_module(build["env"], cmdline, build["dir"], build["data"], {}, modules, read,
                        names)
    return assemble(v, modules, [s for s, _ in packages], read)


def assemble(v, modules: list, packages: list, read: list) -> Plan:
    get = lambda name: v.get(name).strip()  # noqa: E731
    bindir = get("BINDIR")
    names = [m["name"] for m in modules]
    duplicates = sorted(set(n for n in names if names.count(n) > 1))
    if duplicates:
        raise ResolveError(f"modules built twice: {' '.join(duplicates)}")
    baselibs = [get("APPLICATION_MODULE")] + v.words("APPDEPS") + realmodules(v)
    unknown = [m for m in realmodules(v) if m not in names]
    if unknown:   # Makefile.include:679-681 (..module-check)
        raise ResolveError(f"Error - using unknown modules: {' '.join(unknown)}")
    if v.words("ARCHIVES"):
        raise OutOfScope("ARCHIVES are outside the build of step G3-1")
    linked = sorted(o["object"] for m in modules if m["name"] in baselibs
                    for o in m["objects"])
    link_tool = get("LINKXX") if get("CPPMIX") else get("LINK")
    elf, binfile = get("ELFFILE"), get("BINFILE")
    linkcmd = " ".join(w for w in [link_tool, " ".join(linked), "-lm", v.get("LINKFLAGS"),
                                   f"{get('LINKFLAGPREFIX')}-Map={bindir}/{get('APPLICATION')}.map",
                                   "-o", elf] if w.strip())
    header = get("RIOTBUILD_CONFIG_HEADER_C")
    tools = get("RIOTTOOLS")
    lazysponge = " ".join(w for w in [f"'{get('LAZYSPONGE')}'", get("LAZYSPONGE_FLAGS"),
                                      f"'{header}.in'"] if w)
    headers = [{
        "output": header + ".in", "always": True,
        "command": f"mkdir -p '{os.path.dirname(header)}/' && "
                   f"'{tools}/genconfigheader/genconfigheader.sh' "
                   f"{v.get('CFLAGS_WITH_MACROS')} | {lazysponge}",
    }, {
        "output": header, "depends": [header + ".in"],
        "command": "sed -n -e '1i /* Generated file do not edit */' -e '/^#.*/ p' "
                   f"{header}.in > {header}",
    }]
    for pp in v.words("BUILD_HEADERS"):
        headers.append({"output": pp, "command":
                        f"mkdir -p '{os.path.dirname(pp)}/' && "
                        f"'{tools}/generate_pp_successor_header/generate_pp_successor_header.sh'"
                        f" {get('RIOT_PP_SUCCESSOR_MAX')} > {pp}"})
    files = []
    seen = set()
    for path in v.words("BUILD_FILES"):
        if path in seen:
            continue
        seen.add(path)
        if path == elf:
            continue
        if path == binfile:
            files.append({"output": path, "command": " ".join(
                w for w in [get("OBJCOPY"), get("OFLAGS"), "-Obinary", elf, path] if w)})
        else:
            raise OutOfScope(f"build file {path} is outside the build of step G3-1")
    plan = Plan({
        "schema": PLAN_SCHEMA,
        "application": get("APPLICATION"), "board": get("BOARD"), "cpu": get("CPU"),
        "riotbase": RIOTBASE, "appdir": get("APPDIR"), "bindir": bindir,
        "build_dir": get("BUILD_DIR"),
        "toolchain": {name: v.get(name) for name in sorted(toolchain.PROVIDERS)},
        "tools": {"CC": get("CC"), "LINK": link_tool, "OBJCOPY": get("OBJCOPY"),
                  "SIZE": get("SIZE")},
        "packages": packages,
        "headers": headers,
        "modules": modules,
        "baselibs": baselibs,
        "link": {"output": elf, "objects": linked, "command": linkcmd,
                 "map": f"{bindir}/{get('APPLICATION')}.map",
                 "depends": linked},
        "files": files,
        "size": " ".join(w for w in [get("SIZE"), get("SIZEFLAGS"), elf] if w),
        "data_files": sorted(set(read)),
    })
    return plan


def compile_commands(plan: Plan) -> list:
    """compile_commands.json entries of the plan (as RIOT's
    dist/tools/compile_commands writes them for Make: one per object)."""
    return [{"directory": o["cwd"], "file": o["source"], "output": o["object"],
             "arguments": shlex.split(o["command"])}
            for m in plan["modules"] for o in m["objects"]]
