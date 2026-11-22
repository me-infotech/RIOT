# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Sample of step G2C-1 (clean without Make) and the golden file of GNU Make.

The applications of the scope on nrf52840dk (decision D22). The golden file
holds:

  ## <case>: make -n clean [<app> VAR=VALUE…]   the commands of `clean` for
                                               every case (CASES)
  ## <app>: build products before make clean  files per build directory
  ## <app>: make clean (after make <goal>)     the output of `make clean` in
                                               an application copy that Make
                                               built (stub toolchain, GOALS)
  ## <app>: tree after make clean              every path left in the
                                               temporary directory: the
                                               application copy and BUILD_DIR

The application is a copy outside the tree (`clean` removes inside the
application directory), RIOTBASE and BUILD_DIR on the command line. The
build runs with a stub toolchain (STUBS: the compiler writes the object and
the dependency file, objcopy the output, size nothing) and with stand-in
prepared packages in BUILD_DIR (the state files of pkg/pkg.mk, newer than
every input: no git command, no network). Before `clean` the copy gets
stand-ins of what `clean` must remove or keep (EXTRA). Paths: @RIOTBASE@,
@APPDIR@, @TMP@. The file ends with `## end`.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLDEN = os.path.join(HERE, "golden")
BOARD = "nrf52840dk"
CLI = os.path.join(TOOL, "clean.py")
UMASK = 0o022
APPS = {
    "hello-world": "examples/basic/hello-world",
    "gnrc_networking": "examples/networking/gnrc/networking",
    "bindist": "examples/advanced/bindist",
}
# name -> (application, command line variables)
CASES = {
    "hello-world": ("hello-world", {}),
    "gnrc_networking": ("gnrc_networking", {}),
    "bindist": ("bindist", {}),
    "scanbuild-dir": ("hello-world", {"SCANBUILD_OUTPUTDIR": "scan-build/other"}),
    "bindirbase": ("hello-world", {"BINDIRBASE": "@TMP@/elsewhere"}),
    "in-source-packages": ("hello-world", {"PKG_BUILD_OUT_OF_SOURCE": "0"}),
    "docker": ("hello-world", {"BUILD_IN_DOCKER": "1"}),
}
# the Make goal of the build before `make clean` (bindist: also the
# distribution, which `clean` keeps) and the just recipes that build the same
GOALS = {"hello-world": "all", "gnrc_networking": "all", "bindist": "bindist"}
JUST_BUILDS = {"hello-world": ["build"], "gnrc_networking": ["build"],
               "bindist": ["build", "bindist"]}
# stand-ins put into the application copy before `clean`: removed by clean
# (scan-build reports of the board) or kept (another board, other reports)
EXTRA = ("scan-build/nrf52840dk/index.html", "scan-build/native64/index.html",
         "bin/native64/stand-in.o", "bin/cmake-native64/stand-in.o")

for _sub in ("cmake_gen", "resolver", "config_data"):
    sys.path.insert(0, os.path.join(TOOL, "..", _sub))
sys.path.insert(0, TOOL)

STUBS = {
    "arm-none-eabi-gcc": r"""#!/bin/sh
# stub compiler/linker: writes the output (-o) and, with -MD, the dependency file
out= prev= md=
for a in "$@"; do
  case "$prev" in -o) out=$a ;; esac
  case "$a" in -dumpversion) echo 13.3.0; exit 0 ;; -MD) md=1 ;; esac
  prev=$a
done
if [ -n "$out" ] && [ "$out" != /dev/null ]; then
  echo "stand-in $(basename "$out")" > "$out"
  if [ -n "$md" ]; then echo "$out:" > "${out%.o}.d"; fi
fi
exit 0
""",
    "arm-none-eabi-objcopy": '#!/bin/sh\nfor a in "$@"; do last=$a; done\n'
                             'echo "stand-in $(basename "$last")" > "$last"\n',
    "arm-none-eabi-size": "#!/bin/sh\nexit 0\n",
}


def golden_path() -> str:
    return os.path.join(GOLDEN, f"clean__{BOARD}.txt")


def real(variables: dict, tmp: str) -> dict:
    return {k: v.replace("@TMP@", tmp) for k, v in variables.items()}


def shown(variables: dict) -> str:
    return " ".join(shlex.quote(f"{k}={v}") for k, v in variables.items())


def dry_title(case: str) -> str:
    app, variables = CASES[case]
    extra = shown(variables)
    return f"## {case}: make -n clean [{APPS[app]}{' ' + extra if extra else ''}]"


def products_title(app: str) -> str:
    return f"## {app}: build products before make clean (after make {GOALS[app]})"


def output_title(app: str) -> str:
    return f"## {app}: make clean (after make {GOALS[app]})"


def tree_title(app: str) -> str:
    return f"## {app}: tree after make clean"


def make_argv(app_copy: str, riotbase: str, variables: dict, extra: list) -> list:
    return (["make", "--no-print-directory", "-C", app_copy, f"BOARD={BOARD}",
             f"RIOTBASE={riotbase}"] + [f"{k}={v}" for k, v in variables.items()] + extra)


def tool_argv(app_copy: str, variables: dict, extra: list) -> list:
    return ([sys.executable, CLI, "clean", *extra, "-C", app_copy, f"BOARD={BOARD}",
             f"RIOTBASE={RIOTBASE}"] + [f"{k}={v}" for k, v in variables.items()])


def environment(path: str = None, **extra) -> dict:
    # GIT_ALLOW_PROTOCOL=file: a package step that is not up to date fails
    # instead of downloading
    env = {"PATH": path or os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", "/"), "LC_ALL": "C", "GIT_ALLOW_PROTOCOL": "file"}
    env.update(extra)
    return env


def with_umask():
    os.umask(UMASK)


# --- the temporary tree ---------------------------------------------------------------
def copy_app(riotbase: str, tmp: str, app: str) -> str:
    target = os.path.join(tmp, app)
    shutil.copytree(os.path.join(riotbase, APPS[app]), target, symlinks=True,
                    ignore=shutil.ignore_patterns("bin", "bindist", "scan-build"))
    return target


def write_executable(path: str, text: str):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, 0o755)


def stub_toolchain(tmp: str) -> str:
    """The directory of the stub toolchain (put first on PATH)."""
    directory = os.path.join(tmp, "stub-bin")
    os.makedirs(directory, exist_ok=True)
    for name, text in STUBS.items():
        write_executable(os.path.join(directory, name), text)
    return directory


def _touch(path: str, when: float):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as file:
            file.write(f"stand-in {os.path.basename(path)}\n")
    os.utime(path, (when, when))


def stand_in_packages(app_copy: str, build_dir: str):
    """The packages of the application in BUILD_DIR as Make's package step
    leaves them (pkg/pkg.mk: sparse tag, .git, downloaded, patched,
    Makefile.nrfx copies, prepared, in this order of mtimes), with the source
    files the build compiles. Values from the build plan (step G3-1)."""
    import plan as P  # pylint: disable=import-outside-toplevel
    result = P.build_plan(app_copy, {"BOARD": BOARD, "RIOTBASE": RIOTBASE,
                                     "BINDIR": os.path.join(build_dir, "x"),
                                     "BUILD_DIR": build_dir})
    t0 = time.time() - 6     # newer than the inputs, not in the future
    for spec in result["packages"]:
        src = spec["source_dir"]
        if spec["sparse_paths"]:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            with open(f"{src}.sparse", "w", encoding="utf-8") as file:
                file.write(" ".join(spec["sparse_paths"]) + "\n")
            os.utime(f"{src}.sparse", (t0, t0))
        for module in result["modules"]:
            for obj in module["objects"]:
                if obj["source"].startswith(src + os.sep):
                    _touch(obj["source"], t0)
        copy = spec.get("copy")
        for name in (copy or {}).get("files", []):
            _touch(os.path.join(copy["from"], name), t0)
        os.makedirs(os.path.join(src, ".git"), exist_ok=True)
        os.utime(os.path.join(src, ".git"), (t0 + 1, t0 + 1))
        _touch(os.path.join(src, ".pkg-state.git-downloaded"), t0 + 2)
        _touch(os.path.join(src, ".pkg-state.git-patched"), t0 + 3)
        for name in (copy or {}).get("files", []):
            _touch(os.path.join(copy["to"], name), t0 + 4)
        if copy:
            os.utime(copy["to"], (t0 + 4, t0 + 4))
        _touch(os.path.join(src, ".pkg-state.git-prepared"), t0 + 5)
    tag = os.path.join(build_dir, "CACHEDIR.TAG")
    _touch(tag, t0)


def extra_stand_ins(app_copy: str):
    for name in EXTRA:
        _touch(os.path.join(app_copy, name), time.time())


def tree(directory: str, skip: tuple = ("stub-bin",)) -> list:
    """`path type` of every entry below the directory (sorted, C locale)."""
    entries = []
    for root, dirs, files in os.walk(directory):
        if root == directory:
            dirs[:] = [d for d in dirs if d not in skip]
        entries += [os.path.join(root, n) for n in dirs + files]
    out = []
    for path in sorted(entries, key=lambda p: os.path.relpath(p, directory).encode()):
        mode = os.lstat(path).st_mode
        kind = "dir" if stat.S_ISDIR(mode) else "link" if stat.S_ISLNK(mode) else "file"
        out.append(f"{os.path.relpath(path, directory)} {kind}")
    return out


# --- normalisation and golden file ---------------------------------------------------
def normalise(text: str, pairs: list) -> str:
    for path, name in sorted(pairs, key=lambda p: -len(p[0])):
        text = text.replace(path, name)
    return text


SUBMAKE_RE = re.compile(r'^"make" -C (\S+) clean ?$')


def commands(lines: list) -> list:
    """`make -n clean` lines -> [(package directory or None, command)]: the
    sub-make line of a package (Makefile.include:607) names the package of
    the commands after it, up to the first line of the top level."""
    out, package = [], None
    for line in lines:
        match = SUBMAKE_RE.match(line)
        if match:
            package = match.group(1)
            continue
        out.append((package, line))
    # the commands of the top level (rm -rf BINDIR, rm -rf
    # SCANBUILD_OUTPUTDIR: Makefile.include:608-609) are the last two lines
    return [(p if i < len(out) - 2 else None, c) for i, (p, c) in enumerate(out)]


def plan_commands(result: dict, pairs: list) -> list:
    """The `make` part of the plan in the form of commands()."""
    return [(normalise(e["package"], pairs) if e["package"] else None,
             normalise(e["command"], pairs)) for e in result["clean"]]


def read_golden(path: str = None) -> tuple:
    """(header lines, {section title: [lines]}); `## exit:` stays in the body."""
    with open(path or golden_path(), encoding="utf-8") as file:
        lines = file.read().split("\n")
    if "## end" not in lines:
        raise ValueError(f"{path}: no `## end` line")
    lines = lines[:lines.index("## end")]
    first = next(i for i, line in enumerate(lines) if line.startswith("## "))
    head, sections, title, body = lines[:first], {}, None, []
    for line in lines[first:]:
        if line.startswith("## ") and not line.startswith("## exit:"):
            if title:
                sections[title] = body
            title, body = line, []
        else:
            body.append(line)
    if title:
        sections[title] = body
    return head, sections


def exit_and_lines(body: list) -> tuple:
    status = int(body[0].split(":", 1)[1]) if body and body[0].startswith("## exit:") else None
    return status, [line for line in body[1:] if line] if status is not None else body


def run(argv: list, env: dict = None, cwd: str = RIOTBASE) -> tuple:
    res = subprocess.run(argv, cwd=cwd, env=env or environment(), capture_output=True,
                         text=True, check=False, preexec_fn=with_umask)
    return res.returncode, (res.stdout + res.stderr).rstrip("\n")


# --- one run ---------------------------------------------------------------------------
def dry_case(case: str, tmp: str, make_root: str = None) -> tuple:
    """(status, normalised lines) of `make -n clean` (make_root: the RIOT
    tree Make runs in) or `clean.py -n` (make_root None) for a case."""
    app, variables = CASES[case]
    riotbase = make_root or RIOTBASE
    app_copy = copy_app(riotbase, tmp, app)
    values = real(variables, tmp)
    argv = make_argv(app_copy, make_root, values, ["-n", "clean"]) if make_root else \
        tool_argv(app_copy, values, ["-n"])
    status, text = run(argv)
    pairs = [(riotbase, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
    return status, normalise(text, pairs).split("\n") if text else []


def built_tree(app: str, tmp: str, riotbase: str) -> tuple:
    """(application copy, BUILD_DIR, PATH with the stub toolchain) of a fresh
    temporary tree."""
    app_copy = copy_app(riotbase, tmp, app)
    build_dir = os.path.join(tmp, "build")
    stand_in_packages(app_copy, build_dir)
    path = stub_toolchain(tmp) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")
    return app_copy, build_dir, path


def make_build_and_clean(app: str, tmp: str, make_root: str) -> list:
    """The golden sections of the tree case, from Make."""
    app_copy, build_dir, path = built_tree(app, tmp, make_root)
    env = environment(path)
    argv = lambda extra: make_argv(app_copy, make_root, {"BUILD_DIR": build_dir},  # noqa: E731
                                   extra)
    status, text = run(argv(["-j1", GOALS[app]]), env)
    if status != 0:
        raise RuntimeError(f"make {GOALS[app]} failed:\n{text[-3000:]}")
    products = [products_title(app)] + count_products(app_copy)
    extra_stand_ins(app_copy)
    status, text = run(argv(["clean"]), env)
    pairs = [(make_root, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
    return products + [output_title(app), f"## exit: {status}", normalise(text, pairs),
                       tree_title(app)] + tree(tmp)


def count_products(app_copy: str) -> list:
    """How many files each build directory of the application holds."""
    out = []
    for name in sorted(os.listdir(os.path.join(app_copy, "bin"))):
        files = sum(len(f) for _, _, f in os.walk(os.path.join(app_copy, "bin", name)))
        out.append(f"bin/{name}: {files} files")
    return out
