#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1: the resolver prints what Make printed on the base commit, for every
application and board of the sample (golden files of steps G0-1/G0-2);
P2: it takes as many dependency passes and reads the data of exactly the
files Make read; P3: info-boards-supported; P4: the command line, its
exit codes and the errors for requests outside the data.

No Make is run here: the reference is the golden files.

Run: python3 -m unittest discover -s dist/tools/resolver/tests -v
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
sys.path.insert(0, os.path.join(TOOL, "..", "config_data", "tests"))
sys.path.insert(0, os.path.join(TOOL, "..", "config_data"))

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import resolver  # noqa: E402
import rules as R  # noqa: E402
import sample  # noqa: E402

CLI = os.path.join(TOOL, "resolver.py")
COMPARED = ["info-modules", "info-packages", "info-features-used", "info-features-missing",
            "info-features-provided"] + sample.CPU_TARGETS
BOARDS_GOLDEN = os.path.join(HERE, "golden", "boards-supported.txt")
RESULTS = {}


def resolved(app_dir: str, board: str) -> dict:
    key = (app_dir, board)
    if key not in RESULTS:
        RESULTS[key] = resolver.resolve(os.path.join(sample.RIOTBASE, app_dir), {"BOARD": board})
    return RESULTS[key]


def golden(app: str, board: str) -> dict:
    return sample.read_golden(sample.golden_path(app, board))[1]


def make_list(app: str, app_dir: str, board: str) -> list:
    argv = sample.make_argv(app_dir, board, "info-debug-variable-MAKEFILE_LIST")
    words = " ".join(golden(app, board)[" ".join(argv)][1]).split()
    return [os.path.relpath(os.path.normpath(os.path.join(sample.RIOTBASE, app_dir,
                                                          w.replace(sample.PLACEHOLDER,
                                                                    sample.RIOTBASE))),
                            sample.RIOTBASE) for w in words]


def run(args):
    return subprocess.run([sys.executable, CLI] + args, cwd=sample.RIOTBASE, capture_output=True,
                          text=True, check=False)


class InfoParityTest(unittest.TestCase):
    """P1: 6 pairs x 10 outputs."""

    def test_every_output_of_every_pair(self):
        for app, app_dir, board in sample.pairs():
            entries = golden(app, board)
            result = resolved(app_dir, board)
            for target in COMPARED:
                argv = sample.make_argv(app_dir, board, target)
                with self.subTest(command=" ".join(argv)):
                    status, lines = entries[" ".join(argv)]
                    self.assertEqual(status, 0)
                    self.assertEqual(resolver.info(result, target), lines)

    def test_json_state_agrees_with_the_info_outputs(self):
        result = resolved("examples/basic/hello-world", "nrf52840dk")
        self.assertEqual(result["schema"], 1)
        self.assertEqual((result["cpu"], result["cpu_model"], result["board"]),
                         ("nrf52", "nrf52840xxaa", "nrf52840dk"))
        self.assertEqual(result["modules"], resolver.info(result, "info-modules"))
        self.assertEqual(result["pkg_paths"], ["pkg/cmsis/", "pkg/mpaland-printf/"])


class SameWorkTest(unittest.TestCase):
    """P2: same number of passes, data of the same files."""

    def test_passes_are_the_includes_of_dependency_resolution(self):
        for app, app_dir, board in sample.pairs():
            with self.subTest(app=app, board=board):
                count = make_list(app, app_dir, board).count(
                    "makefiles/dependency_resolution.inc.mk")
                self.assertEqual(resolved(app_dir, board)["passes"], count)

    def test_data_read_is_the_data_of_the_files_make_read(self):
        scope = config_data.load_scope()
        converted = set(config_data.converted_files(scope))
        for app, app_dir, board in sample.pairs():
            with self.subTest(app=app, board=board):
                make_read = {R.yaml_name(p) for p in make_list(app, app_dir, board)
                             if p in converted}
                make_read.add(os.path.join(app_dir, "riot-app.yaml"))   # MAKEFILE_LIST: `Makefile`
                self.assertEqual(set(resolved(app_dir, board)["data_files"]), make_read)


class BoardsSupportedTest(unittest.TestCase):
    """P3: info-boards-supported for the boards of the sample."""

    @classmethod
    def setUpClass(cls):
        cls.entries, command = {}, None
        with open(BOARDS_GOLDEN, encoding="utf-8") as file:
            for line in file.read().splitlines():
                if line.startswith("## BOARDS="):
                    command = line[3:]
                    cls.entries[command] = []
                elif command and not line.startswith("## exit:"):
                    cls.entries[command].append(line)

    def test_api_and_command_line(self):
        self.assertEqual(len(self.entries), len(sample.APPS))
        for app_dir in sample.APPS.values():
            command = (f"BOARDS='{' '.join(sample.BOARDS)}' make --no-print-directory -C "
                       f"{app_dir} info-boards-supported")
            with self.subTest(app=app_dir):
                # Make's last line is the list; the line before is the alias
                # message of the top-level make (BOARD unset)
                expected = self.entries[command][-1]
                api = resolver.boards_supported(os.path.join(sample.RIOTBASE, app_dir),
                                                sample.BOARDS)
                self.assertEqual(" ".join(api), expected)
                cli = run(["-C", app_dir, "BOARDS=" + " ".join(sample.BOARDS),
                           "info-boards-supported"])
                self.assertEqual((cli.returncode, cli.stdout), (0, expected + "\n"))


class CommandLineTest(unittest.TestCase):
    """P4."""

    def test_all_targets_of_one_pair(self):
        app, app_dir, board = "gnrc_networking", "examples/networking/gnrc/networking", "native64"
        entries = golden(app, board)
        expected = []
        for target in COMPARED:
            expected += entries[" ".join(sample.make_argv(app_dir, board, target))][1]
        result = run(["-C", app_dir, f"BOARD={board}"] + COMPARED)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), expected)

    def test_json(self):
        result = run(["-C", "examples/basic/hello-world", "BOARD=native64", "json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"cpu": "native"', result.stdout)

    def test_requests_outside_the_data(self):
        for args, text in (
                (["-C", "examples/basic/hello-world", "info-modules"], "is an alias"),
                (["-C", "examples/basic/hello-world", "BOARD=arduino-uno", "info-modules"],
                 "boards/arduino-uno/Makefile.features, which is not converted"),
                (["-C", "tests/sys/shell", "BOARD=native64", "info-modules"],
                 "riot-app.yaml does not exist"),
                (["-C", "examples/basic/hello-world", "BOARD=nrf52840dk", "USEPKG=lwip",
                  "info-modules"], "pkg/lwip/Makefile.dep, which is not converted")):
            with self.subTest(args=args):
                result = run(args)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("outside the data", result.stderr)
                self.assertIn(text, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_errors_of_the_configuration(self):
        result = run(["-C", "examples/basic/hello-world", "BOARD=nrf52840dk",
                      "FEATURES_REQUIRED=periph_eth", "info-modules"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("There are unsatisfied feature requirements: periph_eth", result.stderr)
        result = run(["-C", "examples/basic/hello-world", "BOARD=no-such-board", "info-cpu"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("The specified board no-such-board does not exist.", result.stderr)

    def test_usage_errors(self):
        for args in ([], ["-x", "info-modules"], ["BOARD=native64", "info-nothing"],
                     ["info-boards-supported"]):
            with self.subTest(args=args):
                self.assertEqual(run(["-C", "examples/basic/hello-world"] + args).returncode, 1)


if __name__ == "__main__":
    unittest.main()
