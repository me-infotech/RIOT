# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N5: the build without Make depends on Make in no way.

N1 audit-hook trace of the generator for all applications: no Make file is
   opened, no make process is started (positive probes for both detectors).
N2 a stub `make` first on PATH is never called by the whole chain
   (generator, CMake configure, Ninja building the headers); a probe that
   calls make is caught.
N3 static check: only three modules may start processes, and no module
   names make as a program.
N4 the generated files (CMakeLists.txt, riot-build.cmake, build.ninja)
   contain no make call; detector with positive and negative samples.
N5 the Python processes CMake and Ninja start (the generator at configure
   time, lazysponge) are traced too (sitecustomize audit hook).
"""

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sample  # noqa: E402

CMAKE, NINJA = shutil.which("cmake"), shutil.which("ninja")
MAKE_CALL = re.compile(r"(?:^|[\s;&|(\"'=])(?:\$\(MAKE\)|\$\{MAKE\}|g?make)(?=\s|$|[\"';)])",
                       re.M)

TRACER = textwrap.dedent("""
    import os, sys, json
    LOG = os.environ["G3_TRACE_LOG"]
    def is_make_file(path):
        base = os.path.basename(str(path))
        return base.startswith("Makefile") or base.endswith(".mk")
    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)) \\
                and is_make_file(os.fsdecode(args[0])):
            with open(LOG, "a") as f:
                f.write(json.dumps(["open", os.fsdecode(args[0])]) + "\\n")
        elif event in ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.system"):
            argv = args[1] if event != "os.system" else [args[0]]
            argv = [os.fsdecode(a) for a in (argv if isinstance(argv, (list, tuple)) else [argv])]
            with open(LOG, "a") as f:
                f.write(json.dumps(["run", argv]) + "\\n")
    sys.addaudithook(hook)
""")


def write_executable(path, text):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def make_events(events):
    opened = [e[1] for e in events if e[0] == "open"]
    started = [e[1] for e in events if e[0] == "run"
               and os.path.basename(e[1][0]) in ("make", "gmake")]
    return opened, started


class Traced:
    """A directory with sitecustomize.py (the tracer) and a stub make."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = os.path.join(self.tmp.name, "site")
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.site)
        os.makedirs(self.bin)
        with open(os.path.join(self.site, "sitecustomize.py"), "w", encoding="utf-8") as file:
            file.write(TRACER)
        self.trace = os.path.join(self.tmp.name, "trace.log")
        self.stub_log = os.path.join(self.tmp.name, "make.log")
        for name in ("make", "gmake"):
            write_executable(os.path.join(self.bin, name),
                             f'#!/bin/sh\necho "$0 $*" >> "{self.stub_log}"\nexit 2\n')
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""),
                        PYTHONPATH=self.site, G3_TRACE_LOG=self.trace)

    def run(self, argv, **kw):
        return subprocess.run(argv, env=self.env, capture_output=True, text=True, **kw)

    def stub_calls(self):
        if not os.path.exists(self.stub_log):
            return []
        with open(self.stub_log, encoding="utf-8") as file:
            return file.read().split("\n")[:-1]

    def cleanup(self):
        self.tmp.cleanup()


class TraceTest(unittest.TestCase):
    """N1: the generator for every application of the scope."""

    def setUp(self):
        self.t = Traced()

    def tearDown(self):
        self.t.cleanup()

    def plan(self, app_dir):
        script = (f"import sys; sys.path.insert(0, {TOOL!r}); import plan; "
                  f"plan.build_plan({app_dir!r}, {{'BOARD': 'nrf52840dk', "
                  f"'BUILD_DIR': '/nonexistent-g3', 'BINDIR': '/nonexistent-g3/bin'}})")
        return self.t.run([sys.executable, "-c", script], cwd=sample.RIOTBASE)

    def test_generator_opens_no_make_file_and_starts_no_make(self):
        for app_dir in sample.APPS.values():
            with self.subTest(app=app_dir):
                res = self.plan(app_dir)
                self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        events = read_log(self.t.trace)
        self.assertTrue(any(e[0] == "run" for e in events), "probes ran (tracer works)")
        self.assertEqual(make_events(events), ([], []))
        self.assertEqual(self.t.stub_calls(), [])

    def test_probes_of_the_detectors(self):
        script = ("import subprocess; open('Makefile.include').read(); "
                  "subprocess.run(['make', '--version'])")
        self.t.run([sys.executable, "-c", script], cwd=sample.RIOTBASE)
        opened, started = make_events(read_log(self.t.trace))
        self.assertEqual(opened, ["Makefile.include"])
        self.assertEqual(started, [["make", "--version"]])
        self.assertEqual(len(self.t.stub_calls()), 1)


@unittest.skipIf(CMAKE is None or NINJA is None, "cmake and ninja are needed")
class ChainTest(unittest.TestCase):
    """N2, N4, N5: generator, CMake (configure, Ninja generator), Ninja."""

    def test_whole_chain_without_make(self):
        t = Traced()
        try:
            builddir = os.path.join(t.tmp.name, "cmake")
            gen = [sys.executable, os.path.join(TOOL, "cmake_gen.py"), "generate", "-C",
                   sample.APPS["gnrc_networking"], "BOARD=nrf52840dk", "-B", builddir,
                   f"BUILD_DIR={os.path.join(t.tmp.name, 'build')}"]
            self.assertEqual(t.run(gen, cwd=sample.RIOTBASE).returncode, 0)
            res = t.run([CMAKE, "-G", "Ninja", "-DRIOT_NO_PACKAGES=ON", "-S",
                         os.path.join(builddir, "project"), "-B", builddir])
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            res = t.run([NINJA, "-C", builddir, os.path.join(builddir, "riotbuild", "riotbuild.h"),
                         os.path.join(builddir, "preprocessor", "preprocessor_successor.h")])
            self.assertEqual(res.returncode, 0, res.stdout[-2000:])
            events = read_log(t.trace)
            ran = [e[1] for e in events if e[0] == "run"]
            # N5: the generator, started by CMake's configure step, was traced
            # (its git probe is one of the processes it started)
            self.assertTrue(any(os.path.basename(argv[0]) == "git" for argv in ran), ran)
            self.assertEqual(make_events(events), ([], []))
            self.assertEqual(t.stub_calls(), [])     # N2
            for name in ("project/CMakeLists.txt", "riot-build.cmake", "build.ninja"):
                with self.subTest(file=name):      # N4
                    with open(os.path.join(builddir, name), encoding="utf-8") as file:
                        self.assertEqual(MAKE_CALL.findall(file.read()), [])
        finally:
            t.cleanup()


class MakeCallDetectorTest(unittest.TestCase):
    """N4: the detector finds make calls and ignores words containing make."""

    def test_finds_calls(self):
        for text in ("make all", "cd x && make -C y", '"make" -C pkg', "$(MAKE) -C x",
                     "command = /bin/sh -c 'gmake x'", "COMMAND make", "x;make"):
            with self.subTest(text=text):
                self.assertTrue(MAKE_CALL.findall(text))

    def test_ignores_other_words(self):
        for text in ("cmake --build b", "/usr/bin/cmake -E echo", "makefiles/cflags.build.yaml",
                     "CMAKE_MAKE_PROGRAM", "remake", "make_it.sh", "Makefile.include",
                     "-DMODULE_MAKE_X"):
            with self.subTest(text=text):
                self.assertEqual(MAKE_CALL.findall(text), [])


class StaticTest(unittest.TestCase):
    """N3: imports and program names in the code of the build."""

    MAY_START_PROCESSES = {"toolchain.py", "pkg_prepare.py", "cmake_gen.py"}

    @staticmethod
    def sources():
        return sorted(os.path.join(TOOL, f) for f in os.listdir(TOOL) if f.endswith(".py"))

    @staticmethod
    def problems(text):
        tree = ast.parse(text)
        imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        process = sorted(imports & {"subprocess", "os.system", "pty", "multiprocessing"})
        makes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                 and isinstance(n.value, str) and MAKE_CALL.search(n.value)
                 and not n.value.lstrip().startswith(("#", "Make", "make "))
                 or isinstance(n, ast.Constant) and n.value in ("make", "gmake")]
        return process, makes

    def test_only_three_modules_start_processes_and_none_calls_make(self):
        for path in self.sources():
            with open(path, encoding="utf-8") as file:
                process, makes = self.problems(file.read())
            with self.subTest(module=os.path.basename(path)):
                if os.path.basename(path) not in self.MAY_START_PROCESSES:
                    self.assertEqual(process, [])
                self.assertEqual([m for m in makes if m in ("make", "gmake")], [])

    def test_probe(self):
        process, makes = self.problems("import subprocess\nsubprocess.run(['make', 'all'])\n")
        self.assertEqual(process, ["subprocess"])
        self.assertIn("make", makes)


if __name__ == "__main__":
    unittest.main()
