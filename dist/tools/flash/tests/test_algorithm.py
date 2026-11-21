#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A6: the algorithm of `flash` (flash.py), each part on its own.

A1 exports: GNU Make's target-export-variables (a defined variable reaches
   the flasher whatever the target; an undefined one only, empty, for the
   literal target `flash`); a live GNU Make sample confirms the rule
A2 the `command` condition asks /bin/sh (`command -v`), stub on PATH
A3 the flash data of a Make file is read before its build data, an include
   inside flash data reads only flash data, a file without flash data stops
   (out of scope); the programmer's data after the CPU's Make file
A4 requests outside the data stop with exit status 3 (IOTLAB_NODE,
   BUILD_IN_DOCKER, MOST_RECENT_PORT, a programmer without data, native64)
A5 Make's checks: unsupported programmer warning, FLASHFILE missing (exit 2),
   flasher missing (exit 1 with Make's message), failing flasher (exit 1)
A6 recipe lines: `@` and the other prefixes, the wrapper script
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import flash  # noqa: E402  (sets up the import path)
import buildeval  # noqa: E402
import harness  # noqa: E402
import sample  # noqa: E402

MAKE = shutil.which("make")
HELLO = sample.APPS["hello-world"]


def evaluator(rules_by_file: dict, tmp: str):
    v = buildeval.BuildVariables({})
    ev = flash.FlashEvaluator(v, tmp)
    for name, text in rules_by_file.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as file:
            file.write(text)
    return ev


class ExportTest(unittest.TestCase):
    """A1."""

    def run_rules(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            ev = evaluator({"flash.yaml": text}, tmp)
            ev.v.set("BUILD_EXPORTED", "")
            ev.run_file(os.path.join(tmp, "flash.yaml"))
            return flash.flasher_environment(ev)

    def test_defined_variable_reaches_every_target(self):
        env = self.run_rules("schema: 3\nrules:\n  - set: {var: A, value: a}\n"
                             "  - export: {targets: debug, vars: [A]}\n")
        self.assertEqual(env, {"A": "a"})

    def test_undefined_variable_only_for_literal_flash(self):
        env = self.run_rules("schema: 3\nrules:\n"
                             "  - export: {targets: flash reset, vars: [B]}\n"
                             "  - export: {targets: 'flash% debug', vars: [C]}\n"
                             "  - export: {targets: JLINK_FLASH_TARGETS, vars: [D]}\n")
        self.assertEqual(env, {"B": ""})

    def test_targets_are_expanded_when_the_rule_runs(self):
        env = self.run_rules("schema: 3\nrules:\n  - set: {var: T, value: flash}\n"
                             "  - export: {targets: '${T}', vars: [E]}\n"
                             "  - set: {var: T, value: none}\n")
        self.assertEqual(env, {"E": ""})

    @unittest.skipIf(MAKE is None, "GNU Make is not installed")
    def test_gnu_make_behaves_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Makefile"), "w", encoding="utf-8") as file:
                file.write("include " + os.path.join(sample.RIOTBASE, "makefiles", "utils",
                                                     "variables.mk") + "\n"
                           "A = a\n$(call target-export-variables,debug,A)\n"
                           "$(call target-export-variables,flash reset,B)\n"
                           "$(call target-export-variables,flash% debug,C)\n"
                           "flash:\n\t@env | grep -E '^(A|B|C)=' | sort\n")
            res = subprocess.run(["make", "-s", "-C", tmp, "flash"], capture_output=True,
                                 text=True, check=False)
        self.assertEqual(res.stdout.split(), ["A=a", "B="])


class CommandConditionTest(unittest.TestCase):
    """A2."""

    def test_found_and_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample.write_executable(os.path.join(tmp, "G3Tool"), "#!/bin/sh\n")
            old = os.environ["PATH"]
            os.environ["PATH"] = tmp + os.pathsep + old
            try:
                self.assertTrue(flash.command_found("G3Tool"))
                self.assertFalse(flash.command_found("G3NoSuchTool"))
                self.assertFalse(flash.command_found(""))
                self.assertTrue(flash.command_found(os.path.join(tmp, "G3Tool")))
            finally:
                os.environ["PATH"] = old

    def test_default_programmer_follows_the_probe(self):
        for found, programmer in ((False, "openocd"), (True, "jlink")):
            run = harness.Case(HELLO, {}, found)
            try:
                res = run.tool("--print-env")
            finally:
                run.cleanup()
            with self.subTest(found=found):
                self.assertEqual(res.returncode, 0, res.stderr)
                env = dict(line.split("=", 1) for line in res.stdout.split("\n") if line)
                self.assertEqual("JLINK_DEVICE" in env, programmer == "jlink")
                self.assertEqual("OPENOCD_CONFIG" in env, programmer == "openocd")


class IncludeOrderTest(unittest.TestCase):
    """A3."""

    def test_flash_data_first_then_only_flash_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "sub")
            os.makedirs(sub)
            ev = evaluator({"flash.yaml": "schema: 3\nrules:\n  - add: {ORDER: [flash]}\n"
                                          f"  - include: {{path: '{sub}/x.inc.mk'}}\n",
                            "build.yaml": "schema: 3\nrules:\n  - add: {ORDER: [build]}\n",
                            "Makefile.include": "# not read\n"}, tmp)
            with open(os.path.join(sub, "x.flash.yaml"), "w", encoding="utf-8") as file:
                file.write("schema: 3\nrules:\n  - add: {ORDER: [sub]}\n")
            with open(os.path.join(sub, "x.inc.mk"), "w", encoding="utf-8") as file:
                file.write("# not read\n")
            ev.include_one(os.path.join(tmp, "Makefile.include"), False, "test")
            self.assertEqual(ev.v.words("ORDER"), ["flash", "sub", "build"])
            os.remove(os.path.join(sub, "x.flash.yaml"))
            self.assertRaises(flash.OutOfScope, ev.include_one,
                              os.path.join(tmp, "Makefile.include"), False, "test")

    def test_programmer_data_after_the_cpu(self):
        ev = flash.evaluate(HELLO, {"BOARD": sample.BOARD, "PROGRAMMER": "jlink",
                                    "BINDIR": "/nonexistent-g3/bin"})
        read = ev.flash_read
        self.assertEqual(read, ["boards/nrf52840dk/flash.yaml", "boards/common/nrf52/flash.yaml",
                                "cpu/nrf52/flash.yaml", "cpu/cortexm_common/flash.yaml",
                                "makefiles/tools/jlink.flash.yaml", "makefiles/vars.flash.yaml",
                                "makefiles/tools/programmer.flash.yaml"])
        self.assertLess(ev.read.index("cpu/nrf52/flash.yaml"), ev.read.index("cpu/nrf52/build.yaml"))
        self.assertLess(ev.read.index("makefiles/tools/jlink.flash.yaml"),
                        ev.read.index("makefiles/toolchain/gnu.build.yaml"))


class OutOfScopeTest(unittest.TestCase):
    """A4."""

    def test_exit_3(self):
        for variables in ({"IOTLAB_NODE": "nrf52840dk-1"}, {"BUILD_IN_DOCKER": "1"},
                          {"MOST_RECENT_PORT": "1"}, {"PROGRAMMER": "pyocd"}):
            run = harness.Case(HELLO, variables, False)
            try:
                res = run.tool("-n")
            finally:
                run.cleanup()
            with self.subTest(variables=variables):
                self.assertEqual(res.returncode, 3, res.stderr)
                self.assertIn("error:", res.stderr)

    def test_native64_is_not_converted(self):
        res = subprocess.run([sys.executable, harness.CLI, "flash", "-n", "-C", HELLO,
                              "BOARD=native64"], cwd=sample.RIOTBASE, capture_output=True,
                             text=True, check=False)
        self.assertEqual(res.returncode, 3, res.stderr)


class MakeChecksTest(unittest.TestCase):
    """A5."""

    def test_supported_warning(self):
        v = buildeval.BuildVariables({})
        v.set("PROGRAMMERS_SUPPORTED", "openocd bmp jlink")
        v.set("PROGRAMMER", "jlink")
        self.assertEqual(flash.supported_warning(v), "")
        v.set("PROGRAMMER", "nosuch")
        self.assertEqual(flash.supported_warning(v), "'nosuch' programmer is not supported by "
                         "this board. Supported programmers: 'openocd bmp jlink'")
        v.set("RIOT_CI_BUILD", "1")
        self.assertEqual(flash.supported_warning(v), "")

    def test_unknown_programmer_has_no_flashfile(self):
        run = harness.Case(HELLO, {"PROGRAMMER": "nosuch"}, False)
        try:
            res = run.tool("-n")
        finally:
            run.cleanup()
        self.assertEqual(res.returncode, 2)
        self.assertEqual(res.stderr.split("\n")[:2], [
            "warning: 'nosuch' programmer is not supported by this board. Supported "
            "programmers: 'openocd bmp jlink'",
            "error: FLASHFILE is not defined for this board: nrf52840dk"])

    def test_missing_and_failing_flasher(self):
        for flasher, status, text in (("/nonexistent/flasher", 1, "Flash program "
                                       "/nonexistent/flasher is required but not found in PATH."
                                       "  Aborting."),
                                      ("false", 1, "")):
            run = harness.Case(HELLO, {"PROGRAMMER": "openocd", "FLASHER": flasher}, False)
            try:
                sample.fake_image(run.bindir, HELLO)
                res = run.tool("--no-build")
            finally:
                run.cleanup()
            with self.subTest(flasher=flasher):
                self.assertEqual(res.returncode, status)
                self.assertIn(text, res.stdout)


class RecipeTest(unittest.TestCase):
    """A6."""

    def test_prefixes(self):
        for line, shown in (("@a b", "a b"), ("  @-+a", "a"), ("a @b", "a @b"), ("-a", "a")):
            with self.subTest(line=line):
                self.assertEqual(flash.shown(line), shown)

    def test_wrapper_line_is_silent(self):
        result = flash.plan_flash(HELLO, {"BOARD": sample.BOARD, "PROGRAMMER": "jlink",
                                          "USE_PROGRAMMER_WRAPPER_SCRIPT": "1",
                                          "BINDIR": "/nonexistent-g3/bin"})
        check, command = result["recipe"]
        self.assertTrue(check.startswith("@command -v "))
        self.assertTrue(command.startswith("@" + sample.RIOTBASE + "/dist/tools/programmer/"))
        self.assertIn('--programmer "jlink"', command)


if __name__ == "__main__":
    unittest.main()
