#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""C6: with the generated Make files, GNU Make gives the same results as on
the base commit, and C7: the converted files are exactly those Make reads
for the sample.

The tests run Make live (`make info-*`, `make -n -k`, without a toolchain)
and compare with the golden files recorded on the base commit
(record_golden.py). They are skipped without GNU Make. The build command
list contains compiler flags of the host, so it is compared only on a host
with the compilers named in the golden header.

Run: python3 -m unittest discover -s dist/tools/config_data/tests -v
"""

import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

# pylint: disable=wrong-import-position
import config_data  # noqa: E402
import record_golden  # noqa: E402
import rules as R  # noqa: E402
import sample  # noqa: E402

MAKE = shutil.which("make")
SCOPE = config_data.load_scope()
DEP_OR_FEATURES = (".dep", ".features")


def header_value(header: list, key: str) -> str:
    prefix = f"# {key}: "
    return next(line[len(prefix):] for line in header if line.startswith(prefix))


class GoldenFilesTest(unittest.TestCase):
    """The reference itself: complete and recorded on the base commit."""

    def test_one_golden_file_per_pair_with_every_target(self):
        for app, app_dir, board in sample.pairs():
            with self.subTest(app=app, board=board):
                header, entries = sample.read_golden(sample.golden_path(app, board))
                self.assertEqual(header_value(header, "commit"), SCOPE["base"])
                self.assertEqual(list(entries), [" ".join(sample.make_argv(app_dir, board, t))
                                                 for t in sample.targets(app)])

    def test_sample_is_the_scope_sample(self):
        self.assertEqual(sample.APPS, SCOPE["applications"])
        self.assertEqual(sample.BOARDS, SCOPE["boards"])

    def test_scope_is_what_make_read_on_the_base_commit(self):
        """C7 without Make: MAKEFILE_LIST in the golden files."""
        found = set()
        for app, app_dir, board in sample.pairs():
            _, entries = sample.read_golden(sample.golden_path(app, board))
            argv = sample.make_argv(app_dir, board, "info-debug-variable-MAKEFILE_LIST")
            for word in " ".join(entries[" ".join(argv)][1]).split():
                path = word.replace(sample.PLACEHOLDER + "/", "")
                base = os.path.basename(path)
                if base.startswith("Makefile") and base.endswith(DEP_OR_FEATURES):
                    found.add(os.path.normpath(path))
        self.assertEqual(sorted(found), SCOPE["files"])


NEW_ADAPTERS = ("flash.inc.mk", ".dist.inc.mk", ".clean.inc.mk", "/term.inc.mk", ".term.inc.mk",
                "/debug.inc.mk", ".debug.inc.mk", "/term_providers.inc.mk",
                "/test.inc.mk", ".test.inc.mk")


def without_flash_adapters(result: tuple) -> tuple:
    """MAKEFILE_LIST without the Make adapters generated from the flash data
    (step G3-2, `*flash.inc.mk`), the distribution data (step G3-3,
    `<x>.dist.inc.mk`), the clean data (step G2C-1, `<x>.clean.inc.mk`) and
    the terminal and debugger data with their probes (step G2B-1,
    `term.inc.mk`, `<x>.term.inc.mk`, `debug.inc.mk`, `<x>.debug.inc.mk`,
    `term_providers.inc.mk`) and the test data (step G2B-3, `test.inc.mk`,
    `<x>.test.inc.mk`):
    new files that the Make files of the base commit did not include; the
    settings in them were in those Make files."""
    status, lines = result
    return status, [" ".join(w for w in line.split(" ") if not w.endswith(NEW_ADAPTERS))
                    if "Makefile.include" in line else line for line in lines]


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeParityTest(unittest.TestCase):
    """C6: one live Make run per application, board and target."""

    def compare(self, target_filter):
        for app, app_dir, board in sample.pairs():
            _, entries = sample.read_golden(sample.golden_path(app, board))
            for target in filter(target_filter, sample.targets(app)):
                argv = sample.make_argv(app_dir, board, target)
                with self.subTest(command=" ".join(argv)):
                    self.assertEqual(
                        sample.mask_g003(without_flash_adapters(
                            sample.mask_version(sample.run_make(argv)))),
                        sample.mask_g003(sample.mask_version(entries[" ".join(argv)])))

    def test_info_targets(self):
        self.compare(lambda t: t != sample.BUILD_LIST)

    def test_build_command_list(self):
        header, _ = sample.read_golden(sample.golden_path("hello-world", "native64"))
        now = record_golden.header()
        for key in ("make", "host-gcc", "arm-none-eabi-gcc"):
            if header_value(header, key) != header_value(now, key):
                self.skipTest(f"{key} differs from the golden host: {header_value(now, key)}")
        self.compare(lambda t: t == sample.BUILD_LIST)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveScopeTest(unittest.TestCase):
    """C7 with Make: the files Make reads now are the converted ones."""

    def test_converted_files_are_the_files_make_reads(self):
        self.assertEqual(config_data.make_read_files(SCOPE["applications"], SCOPE["boards"]),
                         SCOPE["files"])

    def test_each_read_file_has_its_yaml(self):
        for path in SCOPE["files"]:
            with self.subTest(path=path):
                self.assertTrue(os.path.isfile(os.path.join(R.RIOTBASE, R.yaml_name(path))))


if __name__ == "__main__":
    unittest.main()
