#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""B9: values where the data first said less than the Make file did; the
generated Make and the build without Make give exactly what the original
Make text gave.

* the branch suffix of the version: `$(addprefix -,$(GIT_BRANCH:master=))`
  (a trailing `master` is cut, also from a longer name);
* SLOT_AUX_OFFSET: `$((ROM_LEN-SLOT_AUX_LEN))` with `NK` accepted in
  ROM_LEN only (`$(ROM_LEN:%K=%*1024)`), as before;
* PKG_VERSION of pkg/cmsis: the two blanks Make kept before the comment are
  part of the value, as before.

Each value is computed by Make from the original text (hard-coded here, as
in the base commit), by Make from the generated file and by the evaluator
of the build without Make from the data.

Run: python3 -m unittest discover -s dist/tools/config_data/build_tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# pylint: disable=wrong-import-position
import common as C  # noqa: E402
from evaluate import Evaluator  # noqa: E402
from variables import Variables  # noqa: E402


def make_value(text: str, name: str, **values) -> str:
    """`[value]` of a variable after Make read `text` (VAR=value on the
    command line)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.mk")
        with open(path, "w", encoding="utf-8") as file:
            file.write(text + f"\n$(info [$({name})])\nall: ;\n")
        res = subprocess.run(["make", "-s", "--no-print-directory", "-f", path]
                             + [f"{k}={v}" for k, v in values.items()],
                             capture_output=True, text=True, env=C.environment(), check=False)
    return res.stdout.split("\n")[0]


def data_value(data: str, name: str, only_set=False, **values) -> str:
    """The value the build without Make reads (only_set: run just the `set`
    of the variable, not the whole file)."""
    v = Variables()
    for key, value in values.items():
        v.command_line(key, value)
    v.set("CURDIR", C.RIOTBASE, "simple")
    rules = C.rules_of(data)
    if only_set:
        rules = [r for r in rules if r.get("set", {}).get("var") == name]
    Evaluator(v, C.RIOTBASE).run(rules)
    return f"[{v.get(name)}]"


def generated_lines(rel: str, *starts) -> str:
    return "\n".join(line for line in C.read(rel).split("\n")
                     if line.startswith(starts))


@unittest.skipIf(C.MAKE is None, "GNU Make is not installed")
class BranchSuffixTest(unittest.TestCase):

    ORIGINAL = "_SUFFIX = $(addprefix -,$(GIT_BRANCH:master=))"
    BRANCHES = ["master", "fix-master", "pr/x-master", "mastery", "main", "HEAD",
                "migration/g0-03-build-flags-data", "master-fix"]

    def test_same_suffix(self):
        generated = generated_lines("makefiles/git_version.inc.mk", "BUILD_GIT_BRANCH_")
        for branch in self.BRANCHES:
            with self.subTest(branch=branch):
                expected = make_value(self.ORIGINAL, "_SUFFIX", GIT_BRANCH=branch)
                self.assertEqual(make_value(generated, "BUILD_GIT_BRANCH_SUFFIX",
                                            GIT_BRANCH=branch), expected)
                self.assertEqual(data_value("makefiles/git_version.build.yaml",
                                            "BUILD_GIT_BRANCH_SUFFIX", PROBE_GIT_BRANCH=branch),
                                 expected)

    def test_expected_values(self):
        self.assertEqual(make_value(self.ORIGINAL, "_SUFFIX", GIT_BRANCH="fix-master"), "[-fix-]")
        self.assertEqual(make_value(self.ORIGINAL, "_SUFFIX", GIT_BRANCH="master"), "[]")


@unittest.skipIf(C.MAKE is None, "GNU Make is not installed")
class SlotAuxTest(unittest.TestCase):

    ORIGINAL = "SLOT_AUX_OFFSET ?= $(shell echo $$(($(ROM_LEN:%K=%*1024)-$(SLOT_AUX_LEN))))"
    ACCEPTED = [("512K", "0"), ("512K", "4096"), ("0x80000", "0x1000"), ("1024K", "8192")]
    REFUSED = [("512K", "4K"), ("0x80000", "1K")]

    def generated(self):
        return generated_lines("sys/slot_aux/Makefile.include", "SLOT_AUX_OFFSET")

    def test_generated_line_is_the_original(self):
        self.assertEqual(self.generated(), self.ORIGINAL)

    def test_accepted_forms(self):
        for rom, aux in self.ACCEPTED:
            with self.subTest(rom=rom, aux=aux):
                expected = make_value(self.ORIGINAL, "SLOT_AUX_OFFSET", ROM_LEN=rom,
                                      SLOT_AUX_LEN=aux)
                self.assertRegex(expected, r"^\[[0-9]+\]$")
                self.assertEqual(make_value(self.generated(), "SLOT_AUX_OFFSET", ROM_LEN=rom,
                                            SLOT_AUX_LEN=aux), expected)
                self.assertEqual(data_value("sys/slot_aux/build.yaml", "SLOT_AUX_OFFSET",
                                            ROM_LEN=rom, SLOT_AUX_LEN=aux), expected)

    def test_refused_forms(self):
        for rom, aux in self.REFUSED:
            with self.subTest(rom=rom, aux=aux):
                # Make: no number for the shell, no value (as before)
                self.assertEqual(make_value(self.ORIGINAL, "SLOT_AUX_OFFSET", ROM_LEN=rom,
                                            SLOT_AUX_LEN=aux), "[]")
                self.assertEqual(make_value(self.generated(), "SLOT_AUX_OFFSET", ROM_LEN=rom,
                                            SLOT_AUX_LEN=aux), "[]")
                # the build without Make stops instead of linking with no value
                with self.assertRaises(ValueError):
                    data_value("sys/slot_aux/build.yaml", "SLOT_AUX_OFFSET",
                               ROM_LEN=rom, SLOT_AUX_LEN=aux)


@unittest.skipIf(C.MAKE is None, "GNU Make is not installed")
class PkgVersionTest(unittest.TestCase):

    ORIGINAL = "PKG_VERSION=2b7495b8535bdcb306dac29b9ded4cfb679d7e5c  # 5.9.0"

    def test_value_with_the_two_blanks(self):
        expected = make_value(self.ORIGINAL, "PKG_VERSION")
        self.assertEqual(expected, "[2b7495b8535bdcb306dac29b9ded4cfb679d7e5c  ]")
        self.assertEqual(make_value(generated_lines("pkg/cmsis/pkg.mk", "PKG_VERSION"),
                                    "PKG_VERSION"), expected)
        self.assertEqual(data_value("pkg/cmsis/pkg.yaml", "PKG_VERSION", only_set=True),
                         expected)

    def test_generated_file_has_no_trailing_blank(self):
        for line in C.read("pkg/cmsis/pkg.mk").split("\n"):
            self.assertEqual(line, line.rstrip())


if __name__ == "__main__":
    unittest.main()
