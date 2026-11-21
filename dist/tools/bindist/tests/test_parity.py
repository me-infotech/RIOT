#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P6: the bindist without Make does what `make bindist` does after
`all`, for every case of the sample (golden file of the base commit,
record_golden.py).

P1 the commands: `bindist.py -n` = `make -n -o all bindist`, line by line
P2 the distribution: `bindist.py --no-build` on stand-in build products
   gives Make's output, exit (success or failure) and bindist/ tree (paths,
   types, modes, sizes, content, kept/new mtimes) and Makefile.distcheck
P3 live Make with the generated adapter gives the golden file (the Make
   side reads the same data); Make's own error line differs only in the line
   number of bindist.inc.mk
P4 live Make and the bindist without Make in this checkout, nothing masked:
   the same Makefile.distcheck (RIOT_VERSION, git describe) and tree
P5 the binaries (opt-in: needs arm-none-eabi-gcc): `make bindist` and
   `just bindist` give the same files and the same bindist.bin
P6 the golden file: header, base commit, every case, `## end`

Run: python3 -m unittest discover -s dist/tools/bindist/tests -v
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import sample  # noqa: E402

MAKE = shutil.which("make")
ARM = shutil.which("arm-none-eabi-gcc")
BASE = "8324f6c5e9"


def sections(lines: list) -> dict:
    """Golden-style lines -> {title: body}."""
    out, title, body = {}, None, []
    for line in "\n".join(lines).split("\n"):
        if line.startswith("## ") and not line.startswith("## exit:"):
            if title:
                out[title] = body
            title, body = line, []
        else:
            body.append(line)
    if title:
        out[title] = body
    return out


def comparable(body: list) -> tuple:
    """(failed, lines without Make's error line) of a run section."""
    status, lines = sample.exit_and_lines(body)
    return status != 0, sample.without_make_messages(lines)


def tool_sections(case: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="g3-bindist-") as tmp:
        return sections(sample.run_case(case, tmp))


def make_sections(case: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="g3-bindist-make-") as tmp:
        return sections(sample.run_case(case, tmp, make_root=sample.RIOTBASE))


def golden_sections() -> dict:
    return sample.read_golden()[1]


class GoldenFilesTest(unittest.TestCase):
    """P6."""

    def test_header_commit_cases_and_end(self):
        head, found = sample.read_golden()
        self.assertTrue(any(line.startswith(f"# commit: {BASE}") for line in head))
        self.assertTrue(any(line.startswith("# make: GNU Make") for line in head))
        expected = []
        for case, (variables, layout) in sample.CASES.items():
            whats = [sample.DRY] + ([sample.RUN, sample.TREE, sample.DISTCHECK] if layout else [])
            expected += [sample.title(case, variables, what) for what in whats]
        self.assertEqual(list(found), expected)

    def test_golden_shows_make_behaviour(self):
        found = golden_sections()
        status, lines = sample.exit_and_lines(found[sample.title("default", {}, sample.DRY)])
        self.assertEqual(status, 0)
        self.assertTrue(lines[1].startswith("for i in Makefile bin/nrf52840dk/abc/*.o "
                                            "bin/nrf52840dk/application_bindist/*.o ; do"))
        tree = found[sample.title("default", {}, sample.TREE)]
        self.assertIn("bin/nrf52840dk/abc/abc.o file 0644 19 84aaf80464c6 mtime=kept", tree)
        status, _ = sample.exit_and_lines(found[sample.title(sample.NO_PRODUCTS, {},
                                                             sample.RUN)])
        self.assertNotEqual(status, 0)


class CommandParityTest(unittest.TestCase):
    """P1."""

    def test_commands(self):
        golden = golden_sections()
        for case, (variables, _) in sample.CASES.items():
            with self.subTest(case=case):
                key = sample.title(case, variables, sample.DRY)
                self.assertEqual(sample.exit_and_lines(tool_sections(case)[key]),
                                 sample.exit_and_lines(golden[key]))


class DistributionParityTest(unittest.TestCase):
    """P2."""

    def test_distribution(self):
        golden = golden_sections()
        for case, (variables, layout) in sample.CASES.items():
            if not layout:
                continue
            found = tool_sections(case)
            with self.subTest(case=case):
                run = sample.title(case, variables, sample.RUN)
                self.assertEqual(comparable(found[run]), comparable(golden[run]))
                for what in (sample.TREE, sample.DISTCHECK):
                    key = sample.title(case, variables, what)
                    self.assertEqual(found[key], golden[key], what)
                if case == sample.NO_PRODUCTS:   # the tool's exit status for a failed command
                    self.assertEqual(sample.exit_and_lines(found[run])[0], 1)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """P3."""

    def test_live_make_gives_the_golden_file(self):
        golden = golden_sections()
        for case in sample.CASES:
            found = make_sections(case)
            with self.subTest(case=case):
                self.assertEqual(list(found), [t for t in golden if f"## {case}: " in t])
                for key, body in found.items():
                    if key.split(": ", 1)[1].startswith(sample.RUN + " "):
                        self.assertEqual(sample.exit_and_lines(body)[0],
                                         sample.exit_and_lines(golden[key])[0])
                        self.assertEqual(comparable(body), comparable(golden[key]))
                    else:
                        self.assertEqual(body, golden[key], key)


@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class UnmaskedTest(unittest.TestCase):
    """P4."""

    def run_both(self, case):
        out = {}
        for who, root in (("make", sample.RIOTBASE), ("tool", None)):
            with tempfile.TemporaryDirectory(prefix=f"g3-bindist-{who}-") as tmp:
                app_copy = sample.prepare(sample.RIOTBASE, tmp, case)
                variables = sample.real(sample.CASES[case][0], tmp)
                argv = sample.make_argv(app_copy, root, variables, ["-o", "all", "bindist"]) \
                    if root else sample.tool_argv(app_copy, variables, ["--no-build"])
                status, _ = sample.run(argv)
                dist = os.path.join(app_copy, "bindist")
                own, sample.OWN_SECTION = sample.OWN_SECTION, ()
                try:
                    out[who] = (status, sample.tree(dist),
                                sample.read(os.path.join(dist, "Makefile.distcheck")))
                finally:
                    sample.OWN_SECTION = own
        return out

    def test_same_distcheck_and_tree(self):
        for case in ("default", "riot-version"):
            out = self.run_both(case)
            with self.subTest(case=case):
                self.assertEqual(out["tool"], out["make"])
                self.assertEqual(out["tool"][0], 0)
                distcheck = out["tool"][2]
                self.assertTrue(distcheck[0].startswith("BINDIST_RIOT_VERSION="))
                self.assertNotIn("@", distcheck[0])
                self.assertRegex(distcheck[1], r"^BINDIST_GIT_HEAD=\S+$")


@unittest.skipIf(ARM is None or MAKE is None,
                 "arm-none-eabi-gcc is not installed: the binaries cannot be built here "
                 "(run in the riotbuild image, dist/tools/cmake_gen/README.md P5)")
class FirmwareTest(unittest.TestCase):
    """P5."""

    def test_same_binary_distribution(self):
        trees = {}
        for who in ("make", "tool"):
            with tempfile.TemporaryDirectory(prefix=f"g3-bindist-fw-{who}-") as tmp:
                app_copy = sample.copy_app(sample.RIOTBASE, tmp)
                argv = sample.make_argv(app_copy, sample.RIOTBASE, {}, ["bindist"]) \
                    if who == "make" else sample.tool_argv(app_copy, {}, ["-j", "2"])
                status, text = sample.run(argv)
                self.assertEqual(status, 0, text[-2000:])
                dist = os.path.join(app_copy, "bindist")
                with open(os.path.join(dist, "bindist.bin"), "rb") as file:
                    binary = file.read()
                listing = [" ".join(line.split()[:3]) for line in sample.tree(dist)]
                trees[who] = (listing, binary)
        self.assertEqual(trees["tool"][0], trees["make"][0])
        self.assertEqual(trees["tool"][1], trees["make"][1])


if __name__ == "__main__":
    unittest.main()
