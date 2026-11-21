#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""N1: the resolver opens no Make file and starts no process (traced with
Python's audit hooks over the whole sample); N2: with a stub `make` first
on PATH, the stub is never called; N3: the resolver modules import nothing
that starts a process. Each detector has a positive probe: the same check
on a run that does open a Make file / call make must report it.

Run: python3 -m unittest discover -s dist/tools/resolver/tests -v
"""

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(TOOL, "..", "..", ".."))
sys.path.insert(0, os.path.join(TOOL, "..", "config_data", "tests"))

# pylint: disable=wrong-import-position
import sample  # noqa: E402

MODULES = ("resolver.py", "pipeline.py", "evaluate.py", "variables.py")
PROCESS_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                  "os.fork", "os.forkpty", "pty.spawn")

# Runs inside the traced interpreter: install the audit hook first, then
# resolve every pair of the sample and info-boards-supported. argv: log,
# then "resolve" or "probe" (opens a Make file and runs `make --version`).
TRACER = r'''
import json, os, sys
log, mode, tool = sys.argv[1], sys.argv[2], sys.argv[3]
events = []
def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        events.append(["open", os.fsdecode(args[0])])
    elif event.startswith(PROCESS):
        events.append(["process", event])
PROCESS = tuple(sys.argv[4].split(","))
sys.addaudithook(hook)
sys.path.insert(0, tool)
import resolver
from evaluate import OutOfScope
resolver.OutOfScope = OutOfScope
if mode == "resolve":
    for app_dir in json.loads(sys.argv[5]):
        for board in json.loads(sys.argv[6]):
            resolver.resolve(os.path.join(resolver.RIOTBASE, app_dir), {"BOARD": board})
        resolver.boards_supported(os.path.join(resolver.RIOTBASE, app_dir),
                                  json.loads(sys.argv[6]))
    # requests outside the data: the resolver must stop without reading Make
    for app_dir, variables in json.loads(sys.argv[7]):
        try:
            resolver.resolve(os.path.join(resolver.RIOTBASE, app_dir), variables)
        except resolver.OutOfScope:
            events.append(["out_of_scope", app_dir])
else:
    open(os.path.join(resolver.RIOTBASE, "sys", "Makefile.dep")).close()
    import subprocess
    subprocess.run(["make", "--version"], capture_output=True)
with open(log, "w") as f:
    json.dump(events, f)
'''


# requests the data does not cover (an unconverted board, package and
# application): traced as well
OUTSIDE = [["examples/basic/hello-world", {"BOARD": "arduino-uno"}],
           ["examples/basic/hello-world", {"BOARD": "nrf52840dk", "USEPKG": "lwip"}],
           ["tests/sys/shell", {"BOARD": "native64"}]]


def is_make_file(path: str) -> bool:
    """A file of GNU Make: `Makefile`, `Makefile.*` or `*.mk`."""
    base = os.path.basename(path)
    return base == "Makefile" or base.startswith("Makefile.") or base.endswith(".mk")


def traced(mode: str) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        script, log = os.path.join(tmp, "tracer.py"), os.path.join(tmp, "events.json")
        with open(script, "w", encoding="utf-8") as file:
            file.write(TRACER)
        subprocess.run([sys.executable, script, log, mode, TOOL, ",".join(PROCESS_EVENTS),
                        json.dumps(list(sample.APPS.values())), json.dumps(sample.BOARDS),
                        json.dumps(OUTSIDE)],
                       check=True, capture_output=True)
        with open(log, encoding="utf-8") as file:
            return json.load(file)


def problems(events: list) -> list:
    return [e for e in events if e[0] == "process" or (e[0] == "open" and is_make_file(e[1]))]


class DetectorTest(unittest.TestCase):

    def test_make_file_names(self):
        for path, result in (("sys/Makefile.dep", True), ("Makefile", True),
                             ("cpu/nrf52/Makefile.nrf802154.dep", True),
                             ("makefiles/stdio.inc.mk", True), ("Makefile.include", True),
                             ("sys/deps.yaml", False), ("makefiles/stdio.inc.yaml", False),
                             ("examples/x/riot-app.yaml", False), ("features.yaml", False),
                             ("mk.yaml", False)):
            with self.subTest(path=path):
                self.assertIs(is_make_file(path), result)

    def test_positive_probe_of_the_trace(self):
        found = problems(traced("probe"))
        self.assertTrue(any(e[0] == "open" and e[1].endswith("sys/Makefile.dep") for e in found))
        self.assertTrue(any(e[0] == "process" for e in found))


class NoMakeFileOpenedTest(unittest.TestCase):
    """N1 over the whole sample (6 pairs and info-boards-supported)."""

    def test_trace(self):
        events = traced("resolve")
        opened = [e[1] for e in events if e[0] == "open"]
        self.assertTrue(any(p.endswith("riot-app.yaml") for p in opened))     # the trace works
        self.assertTrue(any(p.endswith("sys/deps.yaml") for p in opened))
        self.assertEqual(len([e for e in events if e[0] == "out_of_scope"]), len(OUTSIDE))
        self.assertEqual(problems(events), [])


class StubMakeTest(unittest.TestCase):
    """N2: a `make` first on PATH that records each call."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmp.cleanup)
        self.record = os.path.join(tmp.name, "calls")
        stub = os.path.join(tmp.name, "make")
        with open(stub, "w", encoding="utf-8") as file:
            file.write(f'#!/bin/sh\necho "make $*" >> "{self.record}"\nexit 1\n')
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
        self.env = {**os.environ, "PATH": tmp.name + os.pathsep + os.environ.get("PATH", "")}

    def calls(self) -> list:
        if not os.path.exists(self.record):
            return []
        with open(self.record, encoding="utf-8") as file:
            return file.read().splitlines()

    def test_positive_probe_the_stub_is_found_and_records(self):
        subprocess.run(["make", "info-modules"], env=self.env, check=False)
        self.assertEqual(self.calls(), ["make info-modules"])

    def test_resolver_never_calls_make(self):
        for app, app_dir, board in sample.pairs():
            with self.subTest(app=app, board=board):
                result = subprocess.run(
                    [sys.executable, os.path.join(TOOL, "resolver.py"), "-C", app_dir,
                     f"BOARD={board}", "info-modules", "info-cpu", "json"],
                    cwd=RIOTBASE, env=self.env, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])


class StaticTest(unittest.TestCase):
    """N3."""

    PROCESS_RE = re.compile(r"\b(subprocess|os\.system|os\.popen|os\.exec\w*|os\.spawn\w*|"
                            r"pty)\b")

    def test_detector_samples(self):
        for text, result in (("import subprocess", True), ("os.system('make')", True),
                             ("os.execvp(x)", True), ("os.path.exists(p)", False),
                             ("# runs no make", False)):
            with self.subTest(text=text):
                self.assertIs(bool(self.PROCESS_RE.search(text)), result)

    def test_modules_start_no_process(self):
        for name in MODULES:
            with self.subTest(module=name):
                with open(os.path.join(TOOL, name), encoding="utf-8") as file:
                    self.assertIsNone(self.PROCESS_RE.search(file.read()))


if __name__ == "__main__":
    unittest.main()
