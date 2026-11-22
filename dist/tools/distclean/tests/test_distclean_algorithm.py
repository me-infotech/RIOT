#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A7: the algorithm of `distclean` without Make (clean.py distclean).

A1 Makefile.include:624-626: per PKG_PATHS entry in Make's order the
   package's distclean, then rm -rf BINDIRBASE in the application directory;
   which lines Make prints (pkg/pkg.mk: no `@`; Makefile.include: `-@`)
A2 pkg/pkg.mk:178-188: the package's distclean is its clean (the same
   function as `clean`, single source) followed by rm -rf PKG_SOURCE_DIR;
   in-source packages: `git clean`, then rm -rf of the source directory
A3 the build directory of `just build`: nothing when it is below
   BINDIRBASE (default, -B below <app>/bin), rm -rf otherwise
A4 running removes exactly the plan: Make's BINDIRBASE (every board, the
   build directory of `just build`), the package sources of the
   application's packages; scan-build reports, other packages, the
   application stay
A5 Make's error handling: a failing line of a package (no `-`) ends that
   package's sub-make, the next package and the top level go on; a failing
   top-level line is ignored; exit 0
A6 exit status: 3 outside the data (native64, PKG_SOURCE_LOCAL, an
   application without data), 2 a configuration error, 4 refused
A7 `-n` prints the plan and removes nothing
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402
import clean as C  # noqa: E402
from dsample import Tree, variables  # noqa: E402

HELLO = "hello-world"
PKGS = (f"{D.RIOTBASE}/pkg/cmsis/", f"{D.RIOTBASE}/pkg/mpaland-printf/")


class MakePartTest(unittest.TestCase):
    """A1, A2."""

    def test_order_commands_and_echo(self):
        app = os.path.join(D.RIOTBASE, D.APPS[HELLO])
        result = C.plan_distclean(app, variables())
        bindir, src = f"{app}/bin/{D.BOARD}", f"{D.RIOTBASE}/build/pkg"
        cwd = [p.rstrip("/") for p in PKGS]
        self.assertEqual([(e["package"], e["command"], e["echo"], e["origin"], e["cwd"],
                           e["ignore"]) for e in result["clean"]], [
            (PKGS[0], f"rm -rf {bindir}/pkg-build/cmsis", True, "pkg/pkg.mk:184", cwd[0], False),
            (PKGS[0], f"rm -rf {src}/cmsis", True, "pkg/pkg.mk:188", cwd[0], False),
            (PKGS[1], f"rm -rf {bindir}/pkg-build/mpaland-printf", True, "pkg/pkg.mk:184",
             cwd[1], False),
            (PKGS[1], f"rm -rf {src}/mpaland-printf", True, "pkg/pkg.mk:188", cwd[1], False),
            (None, f"rm -rf {app}/bin", False, "Makefile.include:626", app, True)])
        self.assertEqual(result["build"], [])
        self.assertEqual((result["target"], result["packages"], result["whole"]),
                         ("distclean", list(PKGS), [f"{app}/bin"]))
        self.assertIn(f"{src}", result["roots"])

    def test_package_distclean_is_its_clean_then_the_source(self):
        """Single source: the clean lines of a package are those of `clean`."""
        app = os.path.join(D.RIOTBASE, D.APPS[HELLO])
        for values in ({}, {"PKG_BUILD_OUT_OF_SOURCE": "0"}):
            with self.subTest(values=values):
                clean = C.plan_clean(app, variables(**values))["clean"]
                dist = C.plan_distclean(app, variables(**values))["clean"]
                for pkg in PKGS:
                    c = [e for e in clean if e["package"] == pkg]
                    d = [e for e in dist if e["package"] == pkg]
                    self.assertEqual(d[:-1], c)
                    self.assertEqual(d[-1]["origin"], "pkg/pkg.mk:188")

    def test_in_source_packages(self):
        app = os.path.join(D.RIOTBASE, D.APPS[HELLO])
        result = C.plan_distclean(app, variables(PKG_BUILD_OUT_OF_SOURCE="0"))
        src = f"{app}/bin/{D.BOARD}/pkg/cmsis"
        first, second = result["clean"][:2]
        self.assertEqual((first["origin"], first["test_dir"], first["echo"], first["ignore"]),
                         ("pkg/pkg.mk:181", src, False, True))
        self.assertEqual(second["command"], f"rm -rf {src}")

    def test_git_clean_then_source_removed_on_a_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "bin", "pkg", "cmsis")
            os.makedirs(src)
            subprocess.run(["git", "init", "-q", src], check=True)
            for name in ("untracked.o", ".pkg-state.git-prepared"):
                with open(os.path.join(src, name), "w", encoding="utf-8") as file:
                    file.write("x\n")
            entries = [C.git_clean_entry(src, tmp, "pkg/cmsis/"),
                       C.rm_entry(src, tmp, "pkg/pkg.mk:188", True, "pkg/cmsis/", ignore=False)]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(C.run({"target": "distclean", "clean": entries,
                                        "build": []}), 0)
            self.assertFalse(os.path.exists(src))
            self.assertEqual(out.getvalue(), f"rm -rf {src}\n")


class BuildPartTest(unittest.TestCase):
    """A3."""

    def test_build_directory(self):
        app = os.path.join(D.RIOTBASE, D.APPS[HELLO])
        with tempfile.TemporaryDirectory() as tmp:
            build = lambda builddir=None, **v: [  # noqa: E731
                e["command"] for e in C.plan_distclean(app, variables(**v), builddir)["build"]]
            self.assertEqual(build(), [])
            self.assertEqual(build(f"{app}/bin/other"), [])
            self.assertEqual(build(os.path.join(tmp, "b", "x"), BUILD_DIR=os.path.join(tmp, "b")),
                             [f"rm -rf {tmp}/b/x"])
            self.assertEqual(build(BINDIRBASE=os.path.join(tmp, "elsewhere")),
                             [f"rm -rf {app}/bin/cmake-{D.BOARD}"])


class RunTest(unittest.TestCase):
    """A4, A5, A7."""

    def test_removes_exactly_the_plan(self):
        t = Tree()
        try:
            status, out, err = t.distclean()
            self.assertEqual((status, err), (0, ""))
            self.assertEqual(out.split("\n")[:-1], [
                f"rm -rf {t.app}/bin/{D.BOARD}/pkg-build/cmsis",
                f"rm -rf {t.build}/pkg/cmsis",
                f"rm -rf {t.app}/bin/{D.BOARD}/pkg-build/mpaland-printf",
                f"rm -rf {t.build}/pkg/mpaland-printf"])
            self.assertFalse(t.exists("bin"))
            self.assertFalse(t.exists("pkg/cmsis", t.build))
            self.assertFalse(t.exists("pkg/mpaland-printf", t.build))
            for name in t.KEPT:
                self.assertTrue(t.exists(name), name)
            for name in t.KEPT_IN_BUILD_DIR:
                self.assertTrue(t.exists(name, t.build), name)
        finally:
            t.cleanup()

    def test_failing_package_line_ends_its_sub_make(self):
        t = Tree()
        try:
            result = C.plan_distclean(t.app, variables(BUILD_DIR=t.build))
            first = result["clean"][0]
            self.assertEqual(first["package"], PKGS[0])
            result["clean"][0] = dict(first, argv=["false"])
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(C.run(result), 0)
            # the source of cmsis stays (its sub-make stopped), the rest ran
            self.assertTrue(t.exists("pkg/cmsis/CMSIS/x.h", t.build))
            self.assertFalse(t.exists("pkg/mpaland-printf", t.build))
            self.assertFalse(t.exists("bin"))
            self.assertIn("failed with exit status 1: the rest of distclean in "
                          f"{PKGS[0]} is skipped", err.getvalue())
        finally:
            t.cleanup()

    def test_failing_top_level_line_is_ignored(self):
        t = Tree()
        try:
            result = C.plan_distclean(t.app, variables(BUILD_DIR=t.build))
            result["clean"].insert(0, dict(C.rm_entry("/nonexistent/x", t.app, "test", False),
                                           argv=["false"]))
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(C.run(result), 0)
            self.assertIn("distclean: `rm -rf /nonexistent/x` (test) failed with exit status 1 "
                          "(ignored", err.getvalue())
            self.assertFalse(t.exists("bin"))
        finally:
            t.cleanup()

    def test_dry_run_removes_nothing(self):
        t = Tree()
        try:
            status, out, _ = t.distclean("-n")
            self.assertEqual(status, 0)
            self.assertEqual(len(out.split("\n")[:-1]), 5)
            t.assert_untouched(self)
        finally:
            t.cleanup()


class ExitTest(unittest.TestCase):
    """A6."""

    def test_outside_the_data(self):
        t = Tree()
        try:
            self.assertEqual(t.distclean(BOARD="native64")[0], 3)
            self.assertEqual(t.distclean(PKG_SOURCE_LOCAL_CMSIS="/tmp/x")[0], 3)
            self.assertEqual(t.distclean(PKG_SOURCE_LOCAL="/tmp/x")[0], 3)
            os.remove(os.path.join(t.app, "riot-app.yaml"))
            status, _, err = t.distclean()
            self.assertEqual(status, 3)
            self.assertIn("riot-app.yaml does not exist", err)
            t.put("riot-app.yaml")       # the stand-in lists stay complete
            t.assert_untouched(self)
        finally:
            t.cleanup()

    def test_configuration_error(self):
        t = Tree()
        try:
            # git-cache-rs stops the package data (pkg/pkg.build.yaml), exit 2
            status, _, err = t.distclean(GIT_CACHE_RS="/usr/bin/true")
            self.assertEqual(status, 2, err)
            t.assert_untouched(self)
        finally:
            t.cleanup()

    def test_arguments(self):
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as ctx:
            C.main(["distclean", "-C", "x"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("distclean needs -C <application> and BOARD=<board>", err.getvalue())


if __name__ == "__main__":
    unittest.main()
