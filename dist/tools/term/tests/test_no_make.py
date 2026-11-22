#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: the terminal without Make depends on Make in no way.

N1 audit-hook trace of term.py for every application (dry run, environment,
   a run of a stub terminal, `cleanterm`, MOST_RECENT_PORT=1): no Make file
   is opened, no make process is started (positive probes for both
   detectors)
N2 the chain `just term` / `just cleanterm` -> term.py -> terminal, with a
   stub `make`/`gmake` first on PATH that is never called
N3 static check: only term.py starts processes, no module names make as a
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
import harness  # noqa: E402
import sample  # noqa: E402

JUST = shutil.which("just")
MAKE_CALL = re.compile(r"(?:^|[\s;&|(\"'=])(?:\$\(MAKE\)|\$\{MAKE\}|g?make)(?=\s|$|[\"';)])",
                       re.M)
TRACER = textwrap.dedent("""
    import os, sys, json
    LOG = os.environ["G2B_TRACE_LOG"]
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
RECORD = '#!/bin/sh\necho "$(basename "$0") $*" >> "{log}"\nexit {status}\n'


class Traced:
    """sitecustomize.py (the tracer), a stub make/gmake that fails, the stubs
    of the sample."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2b-term-nomake-")   # pylint: disable=consider-using-with
        root = self.tmp.name
        self.site, self.bin = os.path.join(root, "site"), os.path.join(root, "bin")
        os.makedirs(self.site)
        os.makedirs(self.bin)
        with open(os.path.join(self.site, "sitecustomize.py"), "w", encoding="utf-8") as file:
            file.write(TRACER)
        self.trace = os.path.join(root, "trace.log")
        self.make_log = os.path.join(root, "make.log")
        self.term_log = os.path.join(root, "term.log.rec")
        for name in ("make", "gmake"):
            sample.write_executable(os.path.join(self.bin, name),
                                    RECORD.format(log=self.make_log, status=2))
        stubs = sample.make_stubs(os.path.join(root, "stubs"), sample.PATH_TERMINALS)
        self.home = os.path.join(root, "home")
        os.makedirs(self.home)
        self.bindirbase = os.path.join(root, "bin-app")
        self.env = {"PATH": self.bin + os.pathsep + sample.stub_path(stubs), "HOME": self.home,
                    "LC_ALL": "C", "USER": sample.USER, "TMPDIR": root, "PYTHONPATH": self.site,
                    "G2B_TRACE_LOG": self.trace, "G2B_TERM_LOG": self.term_log,
                    "G2B_TTY": "found"}

    def run(self, argv):
        return subprocess.run(argv, env=self.env, capture_output=True, text=True,
                              cwd=sample.RIOTBASE, stdin=subprocess.DEVNULL, check=False)

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

    RUNS = ((["term", "-n"], ["RIOT_TERMINAL=semihosting", "PROGRAMMER=jlink"]),
            (["term", "--print-env"], ["MOST_RECENT_PORT=1", "RIOT_TERMINAL=jlink"]),
            (["term"], ["RIOT_TERMINAL=picocom"]),
            (["term"], ["RIOT_TERMINAL=native"]),
            (["cleanterm", "-n"], ["PROGRAMMER=bmp"]))

    def test_term_opens_no_make_file_and_starts_no_make(self):
        for app_dir in sample.APPS.values():
            for options, variables in self.RUNS:
                t = Traced()
                try:
                    sample.fake_image(os.path.join(t.bindirbase, sample.BOARD), app_dir)
                    res = t.run([sys.executable, harness.CLI, *options, "-C", app_dir,
                                 f"BOARD={sample.BOARD}", f"BINDIRBASE={t.bindirbase}",
                                 *variables])
                    events = t.events()
                    with self.subTest(app=app_dir, options=options, variables=variables):
                        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                        self.assertTrue(any(e[0] == "run" for e in events))   # tracer works
                        if options == ["term"]:
                            self.assertTrue(t.lines(t.term_log))             # terminal ran
                        self.assertEqual(make_events(events), ([], []))
                        self.assertEqual(t.lines(t.make_log), [])
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

    def test_just_term_and_cleanterm_without_make(self):
        for recipe in ("term", "cleanterm"):
            t = Traced()
            try:
                res = t.run([JUST, recipe, sample.APPS["hello-world"], sample.BOARD,
                             "RIOT_TERMINAL=picocom"])
                with self.subTest(recipe=recipe):
                    self.assertEqual(res.returncode, 0, res.stderr[-2000:])
                    calls = t.lines(t.term_log)
                    self.assertTrue(calls[0].startswith("terminal ") and "picocom" in calls[0])
                    self.assertEqual(make_events(t.events()), ([], []))
                    self.assertEqual(t.lines(t.make_log), [])
            finally:
                t.cleanup()


class StaticTest(unittest.TestCase):
    """N3."""

    MAY_START_PROCESSES = {"term.py"}

    @staticmethod
    def problems(text):
        tree = ast.parse(text)
        imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        process = sorted(imports & {"subprocess", "os.system", "pty", "multiprocessing"})
        makes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                 and n.value in ("make", "gmake")]
        return process, makes

    def test_only_term_py_starts_processes_and_none_calls_make(self):
        for name in sorted(f for f in os.listdir(sample.TOOL) if f.endswith(".py")):
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

    def test_recipes_have_no_make_call(self):
        res = subprocess.run([JUST, "--justfile", os.path.join(sample.RIOTBASE, "justfile"),
                              "--dump", "--dump-format", "json"], capture_output=True,
                             text=True, check=True)
        recipes = json.loads(res.stdout)["recipes"]
        for name in ("term", "cleanterm", "generate-term-data"):
            body = json.dumps(recipes[name]["body"])
            with self.subTest(recipe=name):
                self.assertIn("dist/tools/term/term.py", body)
                self.assertEqual(MAKE_CALL.findall(body), [])

    def test_detector(self):
        for text in ("make term", "cd x && make -C y", '"make" -C pkg', "$(MAKE) -C x", "x;gmake"):
            with self.subTest(text=text):
                self.assertTrue(MAKE_CALL.findall(text))
        for text in ("cmake --build b", "makefiles/tools/serial.inc.mk", "remake", "make_it.sh",
                     "Makefile.include", "term.py"):
            with self.subTest(text=text):
                self.assertEqual(MAKE_CALL.findall(text), [])


if __name__ == "__main__":
    unittest.main()
