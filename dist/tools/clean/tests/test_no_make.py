#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1-N4: `clean` without Make depends on Make in no way.

N1 audit-hook trace of `clean.py -n` and `clean.py` for every case of the
   sample on a tree with stand-in build products: no Make file is opened by
   Python, no make process is started (positive probes for both detectors);
   the processes started are rm (and git for in-source packages) only
N2 `just clean` with a stub `make`/`gmake` first on PATH that is never
   called: the build products are gone
N3 static check: only clean.py starts processes, no module names make as a
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
    LOG = os.environ["G2C_TRACE_LOG"]
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
PRODUCTS = (f"bin/{sample.BOARD}/core/x.o", f"bin/{sample.BOARD}/pkg-build/cmsis/y.o",
            f"bin/cmake-{sample.BOARD}/build.ninja", f"scan-build/{sample.BOARD}/index.html")


class Traced:
    """sitecustomize.py (the tracer), a stub make/gmake that fails, an
    application copy with stand-in build products."""

    def __init__(self, app="hello-world"):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2c-clean-nomake-")
        root = self.tmp.name
        self.site, self.bin = os.path.join(root, "site"), os.path.join(root, "stub-bin")
        os.makedirs(self.site)
        os.makedirs(self.bin)
        with open(os.path.join(self.site, "sitecustomize.py"), "w", encoding="utf-8") as file:
            file.write(TRACER)
        self.trace = os.path.join(root, "trace.log")
        self.make_log = os.path.join(root, "make.log")
        for name in ("make", "gmake"):
            sample.write_executable(os.path.join(self.bin, name),
                                    RECORD.format(log=self.make_log, status=2))
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"],
                        PYTHONPATH=self.site, G2C_TRACE_LOG=self.trace)
        self.app = sample.copy_app(sample.RIOTBASE, root, app)
        for name in PRODUCTS:
            sample._touch(os.path.join(self.app, name), 0)  # pylint: disable=protected-access

    def run(self, argv):
        return subprocess.run(argv, env=self.env, capture_output=True, text=True,
                              cwd=sample.RIOTBASE, check=False, preexec_fn=sample.with_umask)

    def events(self):
        if not os.path.exists(self.trace):
            return []
        with open(self.trace, encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    def make_calls(self):
        if not os.path.exists(self.make_log):
            return []
        with open(self.make_log, encoding="utf-8") as file:
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

    def test_clean_opens_no_make_file_and_starts_no_make(self):
        for case, (app, variables) in sample.CASES.items():
            for option in ("-n", None):
                t = Traced(app)
                try:
                    values = sample.real(variables, t.tmp.name)
                    res = t.run(sample.tool_argv(t.app, values, [option] if option else []))
                    events = t.events()
                    with self.subTest(case=case, option=option):
                        self.assertEqual(res.returncode, 0, res.stderr)
                        self.assertTrue(any(e[0] == "start"
                                            and any(a.endswith("clean.py") for a in e[1])
                                            for e in events))
                        self.assertEqual(make_events(events), ([], []))
                        self.assertEqual(t.make_calls(), [])
                        programs = {os.path.basename(e[1][0]) for e in events if e[0] == "run"}
                        # the toolchain probes of the build data (G3-1) may
                        # ask the compiler and git; clean itself runs rm
                        self.assertLessEqual(programs - {"rm", "git", "arm-none-eabi-gcc"},
                                             set(), programs)
                        if option is None and case not in ("bindirbase", "scanbuild-dir"):
                            self.assertIn("rm", programs)
                            for name in PRODUCTS:
                                self.assertFalse(os.path.exists(os.path.join(t.app, name)),
                                                 name)
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
            self.assertEqual(len(t.make_calls()), 1)
        finally:
            t.cleanup()


@unittest.skipIf(JUST is None, "just is not installed")
class ChainTest(unittest.TestCase):
    """N2."""

    def test_just_clean_without_make(self):
        t = Traced()
        try:
            res = t.run([JUST, "clean", t.app, sample.BOARD, f"RIOTBASE={sample.RIOTBASE}"])
            self.assertEqual(res.returncode, 0, res.stderr)
            for name in PRODUCTS:
                self.assertFalse(os.path.exists(os.path.join(t.app, name)), name)
            self.assertTrue(os.path.isfile(os.path.join(t.app, "Makefile")))
            self.assertEqual(make_events(t.events()), ([], []))
            self.assertEqual(t.make_calls(), [])
        finally:
            t.cleanup()


class StaticTest(unittest.TestCase):
    """N3."""

    MAY_START_PROCESSES = {"clean.py"}

    @staticmethod
    def problems(text):
        tree = ast.parse(text)
        imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        process = sorted(imports & {"subprocess", "os.system", "pty", "multiprocessing"})
        makes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                 and n.value in ("make", "gmake")]
        return process, makes

    def test_only_clean_py_starts_processes_and_none_calls_make(self):
        names = sorted(f for f in os.listdir(sample.TOOL) if f.endswith(".py"))
        self.assertEqual(names, ["clean.py", "cleandata.py"])
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
        for name in ("clean", "generate-clean-data"):
            body = json.dumps(recipes[name]["body"])
            with self.subTest(recipe=name):
                self.assertIn("dist/tools/clean/clean.py", body)
                self.assertEqual(MAKE_CALL.findall(body), [])

    def test_detector(self):
        for text in ("make clean", "cd x && make -C y", '"make" -C pkg clean', "$(MAKE) -C x",
                     "x;gmake"):
            with self.subTest(text=text):
                self.assertTrue(MAKE_CALL.findall(text))
        for text in ("cmake --build b", "makefiles/scan-build.inc.mk", "remake", "make_it.sh",
                     "clean.py", "Makefile.include"):
            with self.subTest(text=text):
                self.assertEqual(MAKE_CALL.findall(text), [])


if __name__ == "__main__":
    unittest.main()
