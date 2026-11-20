#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for the migration of the group-1 target `list-ttys` from
Makefile.include (application level) to the root justfile.

Rules (dist/tools/task_layer/README.md):

* R1  `just list-ttys` runs what `make list-ttys` ran: the same command
      (absolute path of ttys.py, no arguments), in the calling directory,
      with the same output and exit code; it works from an application;
* R2  no recipe calls make;
* R3  Make no longer knows `list-ttys`, also inside an application;
* R4  every caller (docs, shell completion) uses just;
* R5  the PORT selection of makefiles/tools/serial.inc.mk, which runs
      ttys.py itself, keeps its behaviour.

Nothing is built and no repository file is changed. Run:
python3 -m unittest discover -s dist/tools/usb-serial/tests -v
"""
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
JUSTFILE = os.path.join(RIOTBASE, "justfile")
APP = os.path.join(RIOTBASE, "examples", "basic", "hello-world")
TTYS = os.path.join(RIOTBASE, "dist", "tools", "usb-serial", "ttys.py")
JUST = shutil.which("just")
MAKE = shutil.which("make")

TARGET = "list-ttys"

# Golden values, recorded with GNU Make 4.3 on branch
# migration/g1-01-print-versions-generate-features (15800305dd) on 2026-11-20, before the
# target was removed; $(RIOTBASE) replaced by the repository root.
#   cd examples/basic/hello-world && make -n list-ttys BOARD=native
MAKE_RAN = TTYS
#   make BOARD=nrf52840dk MOST_RECENT_PORT=1 info-debug-variable-TTY_SELECT_CMD
TTY_SELECT_CMD_NRF52840DK = TTYS + " --most-recent --format path serial --model J-Link"

# Detector for R4: a caller that still runs the Make target.
OLD_CALL = r"(^|[^A-Za-z0-9_./-])make +list-ttys\b"


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def load_task_layer_tests():
    """Reuse the make-call detector of the phase/09 task-layer tests."""
    path = os.path.join(RIOTBASE, "dist", "tools", "task_layer", "tests", "test_justfile.py")
    spec = importlib.util.spec_from_file_location("task_layer_test_justfile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TL = load_task_layer_tests()


def make_has_no_rule(result, target):
    """True if GNU Make reported `target` as unknown (application Makefile)."""
    return (result.returncode != 0
            and f"No rule to make target '{target}'" in result.stderr)


def make_var(app, variable, *args):
    result = run([MAKE, "--no-print-directory", "-C", app, *args,
                  f"info-debug-variable-{variable}"])
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


@unittest.skipIf(JUST is None, "just is not installed")
class JustfileContractTest(unittest.TestCase):
    """R1, R2: the recipe in the parsed justfile and its command."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = TL.dump(JUSTFILE)
        cls.recipe = cls.parsed["recipes"][TARGET]

    def test_recipe_is_public_without_parameters_or_dependencies(self):
        self.assertFalse(self.recipe["private"])
        self.assertEqual(self.recipe["parameters"], [], "Make passed no arguments")
        self.assertEqual(self.recipe["dependencies"], [])

    def test_recipe_runs_in_the_calling_directory_like_make(self):
        self.assertIn("no-cd", self.recipe["attributes"])

    def test_dry_run_prints_the_command_make_ran(self):
        result = run([JUST, "--justfile", JUSTFILE, "--dry-run", TARGET])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), MAKE_RAN)

    def test_found_from_an_application_directory(self):
        # No --justfile: just searches the justfile upwards, as users run it.
        result = run([JUST, "--dry-run", TARGET], cwd=APP)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), MAKE_RAN)

    def test_explicit_justfile_and_working_directory(self):
        result = run([JUST, "--justfile", JUSTFILE, "--working-directory", APP,
                      "--dry-run", TARGET])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), MAKE_RAN)

    def test_no_recipe_calls_make(self):
        self.assertEqual(TL.recipes_calling_make(self.parsed), [])

    def test_make_detector_on_this_recipe_shape(self):
        positive = "@{{ justfile_directory() }}/x/ttys.py && make list-ttys"
        negative = "@{{ justfile_directory() }}/dist/tools/usb-serial/ttys.py"
        for body, expected in ((positive, ["r"]), (negative, [])):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "justfile")
                with open(path, "w", encoding="utf-8") as file:
                    file.write("[no-cd]\nr:\n    " + body + "\n")
                self.assertEqual(TL.recipes_calling_make(TL.dump(path)), expected)


@unittest.skipIf(JUST is None, "just is not installed")
class CallingDirectoryAndArgumentsTest(unittest.TestCase):
    """R1: cwd and arguments, checked with a stub ttys.py in a copied tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        shutil.copy(JUSTFILE, os.path.join(self.root, "justfile"))
        tools = os.path.join(self.root, "dist", "tools", "usb-serial")
        os.makedirs(tools)
        self.stub = os.path.join(tools, "ttys.py")
        TL.write_executable(self.stub, textwrap.dedent("""\
            #!/bin/sh
            echo "cwd=$(pwd)"
            echo "argc=$#"
            exit 7
            """))
        self.app = os.path.join(self.root, "examples", "basic", "app")
        os.makedirs(self.app)

    def test_runs_in_application_directory_without_arguments(self):
        result = run([JUST, TARGET], cwd=self.app)
        self.assertEqual(result.stdout, f"cwd={self.app}\nargc=0\n")
        self.assertEqual(result.returncode, 7, "exit code of ttys.py is passed on")

    def test_extra_arguments_are_rejected(self):
        # make list-ttys had no way to pass arguments to ttys.py.
        result = run([JUST, TARGET, "--serial", "x"], cwd=self.app)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("cwd=", result.stdout)


@unittest.skipIf(JUST is None, "just is not installed")
class OutputParityTest(unittest.TestCase):
    """R1: same stdout, stderr and exit code as ttys.py (no device needed)."""

    def test_same_output_as_ttys_py_from_an_application(self):
        script = run([TTYS], cwd=APP)
        recipe = run([JUST, TARGET], cwd=APP)
        self.assertEqual(recipe.returncode, script.returncode)
        self.assertEqual(recipe.stdout, script.stdout)
        self.assertEqual(recipe.stderr, script.stderr)


@unittest.skipIf(MAKE is None, "make is not installed")
class MakefileTest(unittest.TestCase):
    """R3: Make no longer knows list-ttys."""

    def test_no_rule_or_phony_entry_in_makefiles(self):
        result = run(["git", "grep", "--untracked", "-n", "-E",
                      rf"^{TARGET}\s*:|^\.PHONY:.*\s{TARGET}(\s|$)", "--",
                      "Makefile*", "*.mk", "*/Makefile*"], cwd=RIOTBASE)
        if result.returncode == 128:
            self.skipTest("not a git checkout: " + result.stderr.strip())
        self.assertEqual(result.stdout, "")

    def test_unknown_inside_an_application(self):
        result = run([MAKE, "--no-print-directory", "-n", TARGET, "BOARD=native"], cwd=APP)
        self.assertTrue(make_has_no_rule(result, TARGET), result.stdout + result.stderr)
        self.assertNotIn("ttys.py", result.stdout)

    def test_unknown_in_the_repository_root(self):
        result = run([MAKE, "--no-print-directory", "-n", TARGET], cwd=RIOTBASE)
        self.assertIn(f'unrecognized target "{TARGET}"', result.stdout)

    def test_make_help_no_longer_lists_it(self):
        result = run([MAKE, "--no-print-directory", "help", "BOARD=native"], cwd=APP)
        self.assertEqual(result.returncode, 0, result.stderr)
        targets = result.stdout.split()
        self.assertIn("term", targets, "help output changed format")
        self.assertNotIn(TARGET, targets)


class UnknownTargetDetectorTest(unittest.TestCase):
    """Positive and negative samples for make_has_no_rule()."""

    @staticmethod
    def result(code, stderr):
        return subprocess.CompletedProcess([], code, "", stderr)

    def test_detects_missing_rule(self):
        self.assertTrue(make_has_no_rule(self.result(
            2, "make: *** No rule to make target 'list-ttys'.  Stop.\n"), TARGET))

    def test_ignores_success_and_other_errors(self):
        for code, stderr in ((0, ""),
                             (2, "make: *** No rule to make target 'list-ttys-x'.  Stop."),
                             (2, "make: *** [Makefile.include:824: list-ttys] Error 1")):
            with self.subTest(stderr=stderr):
                self.assertFalse(make_has_no_rule(self.result(code, stderr), TARGET))


@unittest.skipIf(MAKE is None, "make is not installed")
class SerialPortSelectionTest(unittest.TestCase):
    """R5: serial.inc.mk still builds TTY_SELECT_CMD from ttys.py."""

    def test_most_recent_port_command_unchanged(self):
        self.assertEqual(make_var(APP, "TTY_SELECT_CMD", "BOARD=nrf52840dk",
                                  "MOST_RECENT_PORT=1"), TTY_SELECT_CMD_NRF52840DK)

    def test_without_most_recent_port_nothing_is_selected(self):
        self.assertEqual(make_var(APP, "TTY_SELECT_CMD", "BOARD=nrf52840dk",
                                  "MOST_RECENT_PORT=0"), "")
        self.assertEqual(make_var(APP, "PORT", "BOARD=nrf52840dk", "MOST_RECENT_PORT=0"),
                         "/dev/ttyACM0")


class CallerTest(unittest.TestCase):
    """R4: no caller still runs `make list-ttys`."""

    # Named on purpose: history, the migration README and these tests.
    DOCUMENTS_THE_MIGRATION = (
        "release-notes.txt",
        "dist/tools/task_layer",
        "dist/tools/usb-serial/tests",
    )
    CALLERS = (
        "boards/samr21-xpro/doc.md",
        "doc/guides/build-system/flashing.md",
        "doc/guides/networking/rpl.mdx",
    )

    def test_no_reference_to_make_list_ttys(self):
        excludes = [f":(exclude){path}" for path in self.DOCUMENTS_THE_MIGRATION]
        result = run(["git", "grep", "--untracked", "-n", "-E", OLD_CALL, "--", "."]
                     + excludes, cwd=RIOTBASE)
        if result.returncode == 128:
            self.skipTest("not a git checkout: " + result.stderr.strip())
        self.assertEqual(result.stdout, "", "still calls make list-ttys")

    def test_known_callers_use_just(self):
        for path in self.CALLERS:
            with self.subTest(path=path), open(os.path.join(RIOTBASE, path),
                                               encoding="utf-8") as file:
                self.assertIn("just list-ttys", file.read())

    def test_zsh_completion_no_longer_offers_make_target(self):
        path = os.path.join(RIOTBASE, "dist", "tools", "zsh-completion", "zsh-riot.zsh")
        with open(path, encoding="utf-8") as file:
            self.assertNotIn('"list-ttys:', file.read())

    def test_detector_samples(self):
        detector = re.compile(OLD_CALL)
        for text in ("make list-ttys", "    make  list-ttys", "`make list-ttys`"):
            with self.subTest(text=text):
                self.assertTrue(detector.search(text))
        for text in ("just list-ttys", "./list-ttys.sh", "make term", "cmake list-ttys",
                     "make list-ttysx"):
            with self.subTest(text=text):
                self.assertFalse(detector.search(text))


class RegisterTest(unittest.TestCase):
    """The step is registered with this test directory (CI runs it from there)."""

    def test_registered(self):
        path = os.path.join(RIOTBASE, "dist", "tools", "migration", "run_tests.py")
        spec = importlib.util.spec_from_file_location("migration_run_tests", path)
        register = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(register)
        steps = {s["id"]: s for s in register.load()}
        step = steps.get("p3-task-layer-group1-list-ttys")
        self.assertIsNotNone(step, "step missing in steps.yaml")
        self.assertEqual(step["group"], "1")
        self.assertEqual(step["targets"], [{"name": TARGET, "now": "just list-ttys",
                                            "hardware": False}])
        self.assertIn("dist/tools/usb-serial/tests", step["tests"])


@unittest.skipIf(JUST is None, "just is not installed")
class ReachabilityTest(unittest.TestCase):
    """R6 (decision 2026-11-20): `just list-ttys` may be called from any
    directory of the repository, also outside applications and at the root,
    where Make did not know list-ttys. ttys.py lists the host's serial ports and
    uses no application or board context, so the output is the same everywhere."""

    DIRECTORIES = (".", "examples/basic/hello-world", "boards", "sys")

    def test_same_output_from_every_directory(self):
        outputs = set()
        for directory in self.DIRECTORIES:
            with self.subTest(directory=directory):
                result = run([JUST, "list-ttys"], cwd=os.path.join(RIOTBASE, directory))
                outputs.add((result.returncode, result.stdout))
        self.assertEqual(len(outputs), 1, outputs)


if __name__ == "__main__":
    unittest.main()
