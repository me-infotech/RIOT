#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P6: the distclean without Make removes what the application's `make
distclean` removes, plus the build directory of the build without Make when
it is not below BINDIRBASE (golden file of the base commit, record_golden.py).

P1 the plan: for every case the commands of the `make` part (with the
   package each belongs to) are `make -n distclean`'s, in Make's order; the
   `build` part is empty (the build directory of `just build` is below
   BINDIRBASE) or `rm -rf <app>/bin/cmake-<board>` (BINDIRBASE elsewhere)
P2 `clean.py distclean -n` prints the commands of P1 and the build part,
   nothing else
P3 the tree: in a temporary copy, `just build` (and `just bindist` for the
   bindist application) with a stub toolchain, then `just distclean`: the
   same output, exit status and file list as `make <goal>; make distclean`
   of the base commit (application copy and BUILD_DIR); with a directory
   that rm cannot empty (`-locked`): the same tree and exit status, the same
   lines but for Make's diagnostics (README: deliberate differences)
P4 live Make in this checkout: `make -n distclean` gives the golden file;
   `make distclean` on the tree of `just build` leaves the golden tree
P5 the golden file: header, base commit, every case and tree, `## end`

Run: python3 -m unittest discover -s dist/tools/distclean/tests -v
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402
import sample as S  # noqa: E402
import clean as C  # noqa: E402

MAKE = shutil.which("make")
JUST = shutil.which("just")
BASE = "74a0fb9743"
CMAKE_DIR = f"bin/cmake-{D.BOARD}"


def golden():
    return D.read_golden()[1]


def build_part_lines(case: str) -> list:
    """BINDIRBASE elsewhere: the build directory of `just build` stays in
    <app>/bin and is removed separately."""
    return [f"rm -rf @APPDIR@/{CMAKE_DIR}"] if "BINDIRBASE" in D.CASES[case][1] else []


class PlanTest(unittest.TestCase):
    """P1, P2."""

    def test_plan_is_makes_distclean(self):
        sections = golden()
        for case, (app, variables) in D.CASES.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c2-p1-") as tmp:
                status, lines = S.exit_and_lines(sections[D.dry_title(case)])
                self.assertEqual(status, 0)
                app_copy = S.copy_app(D.RIOTBASE, tmp, app)
                result = C.plan_distclean(app_copy, dict(S.real(variables, tmp), BOARD=D.BOARD,
                                                         RIOTBASE=D.RIOTBASE))
                pairs = [(D.RIOTBASE, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
                self.assertEqual(D.plan_commands(result, pairs), D.commands(lines))
                self.assertEqual([S.normalise(e["command"], pairs) for e in result["build"]],
                                 build_part_lines(case))
                self.assertEqual(result["packages"], [f"{D.RIOTBASE}/pkg/cmsis/",
                                                      f"{D.RIOTBASE}/pkg/mpaland-printf/"])
                self.assertEqual(C.refusals(result), [])

    def test_dry_run_prints_the_plan(self):
        sections = golden()
        for case in D.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c2-p2-") as tmp:
                _, lines = S.exit_and_lines(sections[D.dry_title(case)])
                status, out = D.dry_case(case, tmp)
                self.assertEqual(status, 0, out)
                self.assertEqual(out, [c for _, c in D.commands(lines)] + build_part_lines(case))


def just_build(app: str, tmp: str) -> tuple:
    """A temporary tree built without Make (stub toolchain): the application
    copy, BUILD_DIR, the environment for `just`."""
    app_copy, build_dir, path = S.built_tree(app, tmp, D.RIOTBASE)
    env = S.environment(path)
    for recipe in S.JUST_BUILDS[app]:
        status, text = S.run([JUST, recipe, app_copy, D.BOARD, f"RIOTBASE={D.RIOTBASE}",
                              f"BUILD_DIR={build_dir}", "-j", "1"], env)
        if status != 0:
            raise AssertionError(f"just {recipe} failed:\n{text[-3000:]}")
    return app_copy, build_dir, env


def files_below(directory: str) -> int:
    return sum(len(f) for _, _, f in os.walk(directory))


@unittest.skipIf(JUST is None, "just is not installed")
class TreeTest(unittest.TestCase):
    """P3."""

    def test_just_distclean_leaves_makes_tree(self):
        sections = golden()
        for tree, app in D.TREES.items():
            with self.subTest(tree=tree), tempfile.TemporaryDirectory(prefix="g2c2-p3-") as tmp:
                app_copy, build_dir, env = just_build(app, tmp)
                # the build without Make made something to remove
                self.assertGreater(files_below(os.path.join(app_copy, CMAKE_DIR)), 50)
                if app == "bindist":
                    self.assertGreater(files_below(os.path.join(app_copy, "bin", D.BOARD)), 50)
                for name in ("cmsis", "mpaland-printf"):
                    self.assertTrue(os.path.isdir(os.path.join(build_dir, "pkg", name)))
                D.stand_ins(tree, app_copy, build_dir)
                try:
                    status, text = S.run([JUST, "distclean", app_copy, D.BOARD,
                                          f"RIOTBASE={D.RIOTBASE}", f"BUILD_DIR={build_dir}"],
                                         env)
                    left = S.tree(tmp)
                finally:
                    D.unlock(app_copy)
                pairs = [(D.RIOTBASE, "@RIOTBASE@"), (app_copy, "@APPDIR@"), (tmp, "@TMP@")]
                want_status, want = S.exit_and_lines(sections[D.output_title(tree)])
                self.assertEqual(status, want_status, text)
                got = [line for line in S.normalise(text, pairs).split("\n") if line]
                if tree.endswith("-locked"):
                    self.assertEqual(D.without_diagnostics(got), D.without_diagnostics(want))
                    # clean.py reports both failures as Make did (2 lines each)
                    self.assertEqual(len([g for g in got if g.startswith("distclean: ")]), 2)
                else:
                    self.assertEqual(got, want)
                self.assertEqual(left, sections[D.tree_title(tree)])
                # what must stay, stays: scan-build reports, other packages
                for name in (f"scan-build/{D.BOARD}/index.html",
                             "scan-build/native64/index.html"):
                    self.assertTrue(os.path.isfile(os.path.join(app_copy, name)), name)
                for name in D.KEEP_IN_BUILD_DIR:
                    self.assertTrue(os.path.isfile(os.path.join(build_dir, name)), name)


@unittest.skipIf(MAKE is None, "make is not installed")
class LiveMakeTest(unittest.TestCase):
    """P4."""

    def test_live_make_dry_run_equals_golden(self):
        sections = golden()
        for case in D.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="g2c2-p4-") as tmp:
                status, lines = D.dry_case(case, tmp, make_root=D.RIOTBASE)
                self.assertEqual(["## exit: " + str(status)] + lines,
                                 sections[D.dry_title(case)])

    @unittest.skipIf(JUST is None, "just is not installed")
    def test_make_distclean_on_the_tree_of_just_build(self):
        sections = golden()
        tree = "hello-world"
        with tempfile.TemporaryDirectory(prefix="g2c2-p4-") as tmp:
            app_copy, build_dir, env = just_build(tree, tmp)
            D.stand_ins(tree, app_copy, build_dir)
            status, text = S.run(S.make_argv(app_copy, D.RIOTBASE, {"BUILD_DIR": build_dir},
                                             ["distclean"]), env)
            self.assertEqual(status, 0, text)
            self.assertEqual(S.tree(tmp), sections[D.tree_title(tree)])


class GoldenFileTest(unittest.TestCase):
    """P5."""

    def test_golden_file(self):
        head, sections = D.read_golden()
        self.assertTrue(any(line.startswith(f"# commit: {BASE}") for line in head), head)
        titles = [D.dry_title(c) for c in D.CASES]
        for tree in D.TREES:
            titles += [D.products_title(tree), D.output_title(tree), D.tree_title(tree)]
        self.assertEqual(list(sections), titles)
        with open(D.golden_path(), encoding="utf-8") as file:
            self.assertEqual(file.read().rstrip("\n").split("\n")[-1], "## end")


if __name__ == "__main__":
    unittest.main()
