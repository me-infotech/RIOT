#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: `bindist` without Make depends on Make in no way.

N1 audit-hook trace of `bindist.py --no-build` and `-n` for every case of
   the sample: no Make file is opened by Python, no make process is started
   (positive probes for both detectors). The recipe's `cp` copies the
   application's Makefile as a file of the distribution (DIST_FILES), it
   does not read it as Make
N2 the whole chain `just bindist` -> bindist.py -> cmake_gen.py build (G3-1)
   -> cmake/ninja -> the recipe, with a stub `make`/`gmake` first on PATH
   that is never called; cmake and ninja are stubs here (they record their
   arguments; the build itself without Make is N1-N5 of G3-1); a failed
   build makes no distribution
N3 static check: only bindist.py starts processes, no module names make as a
   program
N4 the just recipes have no make call (detector with positive and negative
   samples)
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402

JUST = shutil.which("just")
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
    with open(LOG, "a") as f:
        f.write(json.dumps(["start", list(getattr(sys, "orig_argv", []))]) + "\\n")
""")
RECORD = '#!/bin/sh\necho "$(basename "$0") $*" >> "{log}"\nexit {status}\n'


def write_executable(path: str, text: str):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, 0o755)


class Traced:
    """sitecustomize.py (the tracer), a stub make/gmake that fails, the
    application copy with stand-in build products in Make's BINDIR."""

    def __init__(self, case="default"):
        self.tmp = tempfile.TemporaryDirectory(prefix="g3-bindist-nomake-")
        root = self.tmp.name
        self.site, self.bin = os.path.join(root, "site"), os.path.join(root, "stub-bin")
        os.makedirs(self.site)
        os.makedirs(self.bin)
        with open(os.path.join(self.site, "sitecustomize.py"), "w", encoding="utf-8") as file:
            file.write(TRACER)
        self.trace = os.path.join(root, "trace.log")
        self.make_log = os.path.join(root, "make.log")
        self.tool_log = os.path.join(root, "tools.log")
        for name in ("make", "gmake"):
            write_executable(os.path.join(self.bin, name),
                             RECORD.format(log=self.make_log, status=2))
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"],
                        PYTHONPATH=self.site, G3_TRACE_LOG=self.trace)
        work = os.path.join(root, "work")
        os.makedirs(work)
        self.app = sample.prepare(sample.RIOTBASE, work, case)
        self.bindir = os.path.join(self.app, "bin", sample.BOARD)

    def stub_build_tools(self, status=0):
        for name in ("cmake", "ninja"):
            write_executable(os.path.join(self.bin, name),
                             RECORD.format(log=self.tool_log, status=status))

    def run(self, argv):
        return subprocess.run(argv, env=self.env, capture_output=True, text=True,
                              cwd=sample.RIOTBASE, check=False, preexec_fn=sample.with_umask)

    def events(self):
        if not os.path.exists(self.trace):
            return []
        with open(self.trace, encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    @staticmethod
    def lines(path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as file:
            return file.read().split("\n")[:-1]

    def cleanup(self):
        self.tmp.cleanup()


def make_events(events):
    opened = [e[1] for e in events if e[0] == "open"]
    started = [e[1] for e in events if e[0] == "run"
               and os.path.basename(e[1][0]) in ("make", "gmake")]
    return opened, started


class TraceTest(unittest.TestCase):
    """N1."""

    def test_bindist_opens_no_make_file_and_starts_no_make(self):
        for case, (variables, _) in sample.CASES.items():
            for option in ("--no-build", "-n"):
                t = Traced(case)
                try:
                    values = sample.real(variables, t.tmp.name)
                    res = t.run(sample.tool_argv(t.app, values, [option]))
                    events = t.events()
                    with self.subTest(case=case, option=option):
                        self.assertEqual(res.returncode, 1 if case == sample.NO_PRODUCTS
                                         and option == "--no-build" else 0, res.stderr)
                        # the tracer was loaded into bindist.py
                        self.assertTrue(any(e[0] == "start"
                                            and any(a.endswith("bindist.py") for a in e[1])
                                            for e in events))
                        self.assertEqual(make_events(events), ([], []))
                        self.assertEqual(t.lines(t.make_log), [])
                        if option == "--no-build" and case != sample.NO_PRODUCTS:
                            self.assertTrue(os.path.isfile(os.path.join(t.app, "bindist",
                                                                        "bindist.bin")))
                finally:
                    t.cleanup()

    def test_probes_of_the_detectors(self):
        t = Traced()
        try:
            script = ("import subprocess; open('Makefile.include').read(); "
                      "subprocess.run(['make', '--version'])")
            t.run([sys.executable, "-c", script])
            opened, started = make_events(t.events())
            self.assertEqual(opened, ["Makefile.include"])
            self.assertEqual(started, [["make", "--version"]])
            self.assertEqual(len(t.lines(t.make_log)), 1)
        finally:
            t.cleanup()


@unittest.skipIf(JUST is None, "just is not installed")
class ChainTest(unittest.TestCase):
    """N2."""

    def test_just_bindist_builds_and_distributes_without_make(self):
        t = Traced()
        try:
            t.stub_build_tools()
            res = t.run([JUST, "bindist", t.app, sample.BOARD, f"RIOTBASE={sample.RIOTBASE}",
                         f"BUILD_DIR={os.path.join(t.tmp.name, 'build')}"])
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            events = t.events()
            ran = [e[1] for e in events if e[0] == "run"]
            # the build of step G3-1 ran in Make's BINDIR (traced: cmake started)
            self.assertTrue(any(os.path.basename(a[0]) == "cmake" for a in ran), ran)
            tools = t.lines(t.tool_log)
            self.assertTrue(tools[0].startswith("cmake -G Ninja -S "), tools)
            self.assertTrue(tools[1].startswith(f"cmake --build {t.bindir} -- -j"), tools)
            self.assertTrue(os.path.isfile(os.path.join(t.bindir, "project", "CMakeLists.txt")))
            # then the recipe, with the build products of that directory
            self.assertIn("Copying bin/nrf52840dk/abc/abc.o to bindist.", res.stdout)
            self.assertTrue(os.path.isfile(os.path.join(t.app, "bindist", "bin", sample.BOARD,
                                                        "abc", "abc.o")))
            self.assertEqual(make_events(events), ([], []))
            self.assertEqual(t.lines(t.make_log), [])
        finally:
            t.cleanup()

    def test_failed_build_makes_no_distribution(self):
        t = Traced()
        try:
            t.stub_build_tools(status=1)
            res = t.run([JUST, "bindist", t.app, sample.BOARD, f"RIOTBASE={sample.RIOTBASE}"])
            self.assertNotEqual(res.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(t.app, "bindist")))
            self.assertEqual(t.lines(t.make_log), [])
        finally:
            t.cleanup()


class StaticTest(unittest.TestCase):
    """N3."""

    MAY_START_PROCESSES = {"bindist.py"}

    @staticmethod
    def problems(text):
        tree = ast.parse(text)
        imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        process = sorted(imports & {"subprocess", "os.system", "pty", "multiprocessing"})
        makes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                 and n.value in ("make", "gmake")]
        return process, makes

    def test_only_bindist_py_starts_processes_and_none_calls_make(self):
        names = sorted(f for f in os.listdir(sample.TOOL) if f.endswith(".py"))
        self.assertEqual(names, ["bindist.py", "distdata.py"])
        for name in names:
            with open(os.path.join(sample.TOOL, name), encoding="utf-8") as file:
                process, makes = self.problems(file.read())
            with self.subTest(module=name):
                if name not in self.MAY_START_PROCESSES:
                    self.assertEqual(process, [])
                self.assertEqual(makes, [])

    def test_probe(self):
        process, makes = self.problems("import subprocess\nsubprocess.run(['make', 'all'])\n")
        self.assertEqual((process, makes), (["subprocess"], ["make"]))


@unittest.skipIf(JUST is None, "just is not installed")
class RecipeTest(unittest.TestCase):
    """N4."""

    def test_recipe_has_no_make_call(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True,
                             text=True, check=True)
        recipes = json.loads(res.stdout)["recipes"]
        for name in ("bindist", "generate-dist-data"):
            body = json.dumps(recipes[name]["body"])
            with self.subTest(recipe=name):
                self.assertIn("dist/tools/bindist/bindist.py", body)
                self.assertEqual(MAKE_CALL.findall(body), [])

    def test_detector(self):
        for text in ("make bindist", "cd x && make -C y", '"make" -C pkg', "$(MAKE) -C x",
                     "x;gmake"):
            with self.subTest(text=text):
                self.assertTrue(MAKE_CALL.findall(text))
        for text in ("cmake --build b", "makefiles/bindist.inc.mk", "remake", "make_it.sh",
                     "Makefile.distcheck", "bindist.py"):
            with self.subTest(text=text):
                self.assertEqual(MAKE_CALL.findall(text), [])


if __name__ == "__main__":
    unittest.main()
