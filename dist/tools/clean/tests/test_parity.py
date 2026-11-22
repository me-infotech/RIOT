#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P5: the clean without Make deletes what `make clean` deletes, plus the
build directory of the build without Make (golden file of the base commit,
record_golden.py).

P1 the plan: for every case the commands of the `make` part (with the
   package each belongs to) are `make -n clean`'s, in Make's order; the
   `build` part is exactly `rm -rf <app>/bin/cmake-<board>`
P2 `clean.py -n` prints the commands of P1 and the build directory, nothing
   else
P3 the tree: in a temporary copy, `just build` (and `just bindist` for the
   bindist application) with a stub toolchain, then `just clean`: the same
   output and the same file list as `make <goal>; make clean` of the base
   commit (application copy and BUILD_DIR; stand-ins that must stay or go)
P4 live Make with the generated adapter in this checkout: `make -n clean`
   gives the golden file, and `make clean` on the tree built by `just build`
   leaves the golden tree plus the build directory of `just build`, which
   Make does not know (the mapping of the README)
P5 the golden file: header, base commit, every case and application, `## end`

Run: python3 -m unittest discover -s dist/tools/clean/tests -v
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
import clean as C  # noqa: E402

MAKE = shutil.which("make")
JUST = shutil.which("just")
BASE = "74a0fb9743"
CMAKE_DIR = f"bin/cmake-{sample.BOARD}"


def golden():
    return sample.read_golden()[1]


def build_part_line() -> str:
    return f"rm -rf @APPDIR@/{CMAKE_DIR}"


class PlanTest(unittest.TestCase):
    """P1, P2."""

    def test_plan_is_makes_clean(self):
        sections = golden()
        for case, (app, variables) in sample.CASES.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c-p1-") as tmp:
                status, lines = sample.exit_and_lines(sections[sample.dry_title(case)])
                self.assertEqual(status, 0)
                app_copy = sample.copy_app(sample.RIOTBASE, tmp, app)
                result = C.plan_clean(app_copy, dict(sample.real(variables, tmp),
                                                     BOARD=sample.BOARD, RIOTBASE=sample.RIOTBASE))
                pairs = [(sample.RIOTBASE, "@RIOTBASE@"), (app_copy, "@APPDIR@"),
                         (tmp, "@TMP@")]
                self.assertEqual(sample.plan_commands(result, pairs), sample.commands(lines))
                self.assertEqual([sample.normalise(e["command"], pairs) for e in result["build"]],
                                 [build_part_line()])
                self.assertEqual(result["packages"],
                                 [f"{sample.RIOTBASE}/pkg/cmsis/",
                                  f"{sample.RIOTBASE}/pkg/mpaland-printf/"])

    def test_dry_run_prints_the_plan(self):
        sections = golden()
        for case in sample.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c-p2-") as tmp:
                _, lines = sample.exit_and_lines(sections[sample.dry_title(case)])
                status, out = sample.dry_case(case, tmp)
                self.assertEqual(status, 0, out)
                self.assertEqual(out, [c for _, c in sample.commands(lines)]
                                 + [build_part_line()])


def just_build(app: str, tmp: str) -> tuple:
    """A temporary tree built without Make (stub toolchain): the application
    copy, the environment for `just`."""
    app_copy, build_dir, path = sample.built_tree(app, tmp, sample.RIOTBASE)
    env = sample.environment(path)
    for recipe in sample.JUST_BUILDS[app]:
        status, text = sample.run([JUST, recipe, app_copy, sample.BOARD,
                                   f"RIOTBASE={sample.RIOTBASE}", f"BUILD_DIR={build_dir}",
                                   "-j", "1"], env)
        if status != 0:
            raise AssertionError(f"just {recipe} failed:\n{text[-3000:]}")
    return app_copy, build_dir, env


def files_below(directory: str) -> int:
    return sum(len(f) for _, _, f in os.walk(directory))


@unittest.skipIf(JUST is None, "just is not installed")
class TreeTest(unittest.TestCase):
    """P3."""

    def test_just_clean_leaves_makes_tree(self):
        sections = golden()
        for app in sample.APPS:
            with self.subTest(app=app), tempfile.TemporaryDirectory(prefix="g2c-p3-") as tmp:
                app_copy, build_dir, env = just_build(app, tmp)
                # the build without Make made something to clean
                self.assertGreater(files_below(os.path.join(app_copy, CMAKE_DIR)), 50)
                if app == "bindist":
                    self.assertGreater(files_below(os.path.join(app_copy, "bin",
                                                                sample.BOARD)), 50)
                sample.extra_stand_ins(app_copy)
                status, text = sample.run([JUST, "clean", app_copy, sample.BOARD,
                                           f"RIOTBASE={sample.RIOTBASE}",
                                           f"BUILD_DIR={build_dir}"], env)
                pairs = [(sample.RIOTBASE, "@RIOTBASE@"), (app_copy, "@APPDIR@"),
                         (tmp, "@TMP@")]
                want_status, want = sample.exit_and_lines(sections[sample.output_title(app)])
                self.assertEqual(status, want_status, text)
                # Make prints the lines of pkg/pkg.mk's `clean::` (no `@`)
                got = [line for line in sample.normalise(text, pairs).split("\n") if line]
                self.assertEqual(got, want)
                self.assertEqual(sample.tree(tmp), sections[sample.tree_title(app)])
                # never anything else: what must stay, stays
                for name in ("scan-build/native64/index.html", "bin/native64/stand-in.o",
                             "bin/cmake-native64/stand-in.o"):
                    self.assertTrue(os.path.isfile(os.path.join(app_copy, name)), name)
                self.assertFalse(os.path.exists(os.path.join(app_copy, "scan-build",
                                                             sample.BOARD)))


@unittest.skipIf(MAKE is None, "make is not installed")
class LiveMakeTest(unittest.TestCase):
    """P4."""

    def test_live_make_dry_run_equals_golden(self):
        sections = golden()
        for case in sample.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c-p4-") as tmp:
                status, lines = sample.dry_case(case, tmp, make_root=sample.RIOTBASE)
                self.assertEqual(["## exit: " + str(status)] + lines,
                                 sections[sample.dry_title(case)])

    @unittest.skipIf(JUST is None, "just is not installed")
    def test_make_clean_leaves_only_the_build_directory_of_just_build(self):
        sections = golden()
        app = "hello-world"
        with tempfile.TemporaryDirectory(prefix="g2c-p4-") as tmp:
            app_copy, build_dir, env = just_build(app, tmp)
            sample.extra_stand_ins(app_copy)
            status, text = sample.run(sample.make_argv(app_copy, sample.RIOTBASE,
                                                       {"BUILD_DIR": build_dir}, ["clean"]), env)
            self.assertEqual(status, 0, text)
            left = sample.tree(tmp)
            cmake = [line for line in left if line.startswith(f"{app}/{CMAKE_DIR}")]
            self.assertGreater(len(cmake), 50)
            self.assertEqual([line for line in left if line not in cmake],
                             sections[sample.tree_title(app)])


class GoldenFileTest(unittest.TestCase):
    """P5."""

    def test_golden_file(self):
        head, sections = sample.read_golden()
        self.assertTrue(any(line.startswith(f"# commit: {BASE}") for line in head), head)
        titles = [sample.dry_title(c) for c in sample.CASES]
        for app in sample.APPS:
            titles += [sample.products_title(app), sample.output_title(app),
                       sample.tree_title(app)]
        self.assertEqual(list(sections), titles)
        with open(sample.golden_path(), encoding="utf-8") as file:
            self.assertEqual(file.read().rstrip("\n").split("\n")[-1], "## end")


if __name__ == "__main__":
    unittest.main()
