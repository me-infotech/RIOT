#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A6 (algorithm) and S1-S4 (safety) of `clean` without Make.

A1 the clean data is read where Make includes its owner; its value stays
   recursive (BOARD read late) and a command line value replaces it
A2 Makefile.include:605-611: one package clean per PKG_PATHS entry in
   Make's order, then BINDIR, then SCANBUILD_OUTPUTDIR in the application
   directory; which lines Make prints (pkg/pkg.mk: no `@`)
A3 pkg/pkg.mk:178-185: rm -rf PKG_BUILD_DIR, or `git clean` of the source
   directory of an in-source package (runs on a real repository: untracked
   files go, the state files stay; skipped without the directory); a package
   without package data is outside the data
A4 the build directory of `just build`: default, -B, nothing when it is
   Make's BINDIR or inside it
A5 running: every command, a failing one ignored (Make's `-`), exit 0
A6 exit status: 3 outside the data (native64, an application without data,
   PKG_SOURCE_LOCAL), 2 invalid clean data, 4 refused
S1 a path is one plain word without `..` (no blank, glob, quote, `$`)
S2 below the application's build directories (<app>/bin, BINDIRBASE,
   <app>/scan-build) or RIOT's build directory (BUILD_DIR); `/`, HOME,
   RIOTBASE, the application directory and their parents are never roots
S3 no symbolic link below a root leads out of it
S4 every path is checked before anything is removed: one refusal, nothing
   removed; `-n` refuses as well
(S5, BINDIRBASE removed as a whole, is distclean's: dist/tools/distclean/tests)
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
import sample  # noqa: E402
import clean as C  # noqa: E402

HELLO = "hello-world"


def variables(**extra) -> dict:
    return dict({"BOARD": sample.BOARD, "RIOTBASE": sample.RIOTBASE}, **extra)


class Tree:
    """An application copy in a temporary directory, with stand-ins of the
    build products in Make's BINDIR, the build directory of `just build`
    and the scan-build reports."""

    def __init__(self, app=HELLO):
        self.tmp = tempfile.TemporaryDirectory(prefix="g2c-clean-alg-")
        self.root = self.tmp.name
        self.app = sample.copy_app(sample.RIOTBASE, self.root, app)
        for name in (f"bin/{sample.BOARD}/core/x.o",
                     f"bin/{sample.BOARD}/pkg-build/cmsis/y.o",
                     f"bin/cmake-{sample.BOARD}/build.ninja",
                     f"scan-build/{sample.BOARD}/index.html",
                     "bin/native64/z.o", "scan-build/native64/index.html"):
            self.put(name)

    def put(self, name: str, base: str = None):
        path = os.path.join(base or self.app, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write("stand-in\n")
        return path

    def exists(self, name: str) -> bool:
        return os.path.lexists(os.path.join(self.app, name))

    def clean(self, *args, **values):
        """(exit status, stdout, stderr) of clean.py, in this process."""
        out, err = io.StringIO(), io.StringIO()
        argv = ["clean", "-C", self.app] + list(args) + \
            [f"{k}={v}" for k, v in variables(BUILD_DIR=os.path.join(self.root, "build"),
                                              **values).items()]
        with redirect_stdout(out), redirect_stderr(err):
            status = C.main(argv)
        return status, out.getvalue(), err.getvalue()

    def cleanup(self):
        self.tmp.cleanup()


class EvaluatorTest(unittest.TestCase):
    """A1."""

    def test_clean_data_read_with_the_build_data(self):
        ev = C.evaluate(os.path.join(sample.RIOTBASE, sample.APPS[HELLO]), variables())
        self.assertEqual(ev.clean_read, ["makefiles/scan-build.clean.yaml"])
        self.assertIn("makefiles/scan-build.clean.yaml", ev.read)
        # read where Makefile.include:211 includes scan-build.inc.mk: before build.yaml
        self.assertLess(ev.read.index("makefiles/scan-build.clean.yaml"),
                        ev.read.index("build.yaml"))
        self.assertEqual(ev.v.get("SCANBUILD_OUTPUTDIR"), f"scan-build/{sample.BOARD}")
        self.assertEqual(ev.v.flavor("SCANBUILD_OUTPUTDIR"), "recursive")

    def test_command_line_replaces_the_data(self):
        ev = C.evaluate(os.path.join(sample.RIOTBASE, sample.APPS[HELLO]),
                        variables(SCANBUILD_OUTPUTDIR="reports"))
        self.assertEqual(ev.v.get("SCANBUILD_OUTPUTDIR"), "reports")


class MakePartTest(unittest.TestCase):
    """A2, A3 (out of source)."""

    def test_order_commands_and_echo(self):
        app = os.path.join(sample.RIOTBASE, sample.APPS[HELLO])
        result = C.plan_clean(app, variables())
        bindir = f"{app}/bin/{sample.BOARD}"
        pkg = [f"{sample.RIOTBASE}/pkg/cmsis/", f"{sample.RIOTBASE}/pkg/mpaland-printf/"]
        self.assertEqual([(e["package"], e["command"], e["echo"], e["origin"], e["cwd"])
                          for e in result["clean"]], [
            (pkg[0], f"rm -rf {bindir}/pkg-build/cmsis", True, "pkg/pkg.mk:184",
             pkg[0].rstrip("/")),
            (pkg[1], f"rm -rf {bindir}/pkg-build/mpaland-printf", True, "pkg/pkg.mk:184",
             pkg[1].rstrip("/")),
            (None, f"rm -rf {bindir}", False, "Makefile.include:608", app),
            (None, f"rm -rf scan-build/{sample.BOARD}", False, "Makefile.include:609", app)])
        self.assertEqual(result["packages"], pkg)
        self.assertEqual(result["data"], ["makefiles/scan-build.clean.yaml"])

    def test_package_without_data_is_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "pkg", "x"))
            with open(os.path.join(tmp, "pkg", "x", "Makefile"), "w", encoding="utf-8") as f:
                f.write("include $(RIOTBASE)/pkg/pkg.mk\n")
            with self.assertRaisesRegex(C.OutOfScope, "not converted to package data"):
                C.package_part({}, {}, os.path.join(tmp, "pkg", "x") + "/", [])


class InSourceTest(unittest.TestCase):
    """A3 (in-source packages)."""

    def test_git_clean_entry(self):
        app = os.path.join(sample.RIOTBASE, sample.APPS[HELLO])
        result = C.plan_clean(app, variables(PKG_BUILD_OUT_OF_SOURCE="0"))
        src = f"{app}/bin/{sample.BOARD}/pkg/cmsis"
        entry = result["clean"][0]
        self.assertEqual(entry["command"],
                         f"test -d {src} && git -C {src} --git-dir=.git --work-tree=. "
                         "clean -xdff '**' -e '.pkg-state.git*'")
        self.assertEqual(entry["argv"], ["git", "-C", src, "--git-dir=.git", "--work-tree=.",
                                         "clean", "-xdff", "**", "-e", ".pkg-state.git*"])
        self.assertEqual((entry["test_dir"], entry["echo"], entry["origin"]),
                         (src, False, "pkg/pkg.mk:181"))

    def test_git_clean_runs_on_a_repository(self):
        t = Tree()
        try:
            src = os.path.join(t.app, "bin", sample.BOARD, "pkg", "cmsis")
            os.makedirs(src)
            git = ["git", "-C", src, "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run(["git", "init", "-q", src], check=True)
            t.put("kept.h", src)
            subprocess.run(git + ["add", "kept.h"], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], check=True)
            t.put("untracked.o", src)
            t.put(".pkg-state.git-prepared", src)
            t.put("sub/ignored.o", src)
            result = C.plan_clean(t.app, variables(PKG_BUILD_OUT_OF_SOURCE="0"))
            first = dict(result, clean=result["clean"][:1], build=[])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(C.run(first), 0)
            self.assertEqual(sorted(os.listdir(src)), [".git", ".pkg-state.git-prepared",
                                                       "kept.h"])
            # without the directory nothing runs (`test -d … &&`)
            missing = dict(result, clean=result["clean"][1:2], build=[])
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(C.run(missing), 0)
            self.assertEqual(err.getvalue(), "")
        finally:
            t.cleanup()


class BuildPartTest(unittest.TestCase):
    """A4."""

    def test_build_directory(self):
        app = os.path.join(sample.RIOTBASE, sample.APPS[HELLO])
        bindir = f"{app}/bin/{sample.BOARD}"
        part = lambda builddir: C.build_part(app, variables(), builddir, bindir)  # noqa: E731
        self.assertEqual([e["command"] for e in part(None)],
                         [f"rm -rf {app}/bin/cmake-{sample.BOARD}"])
        self.assertEqual(part(None)[0]["origin"], "cmake_gen.py builddir()")
        self.assertEqual([e["command"] for e in part(f"{app}/bin/other")],
                         [f"rm -rf {app}/bin/other"])
        self.assertEqual(part(bindir), [])
        self.assertEqual(part(f"{bindir}/sub"), [])


class RunTest(unittest.TestCase):
    """A5, A3 on a tree."""

    def test_removes_exactly_the_plan(self):
        t = Tree()
        try:
            status, out, err = t.clean()
            self.assertEqual((status, err), (0, ""))
            self.assertEqual(out.split("\n")[:-1], [
                f"rm -rf {t.app}/bin/{sample.BOARD}/pkg-build/cmsis",
                f"rm -rf {t.app}/bin/{sample.BOARD}/pkg-build/mpaland-printf"])
            for name in (f"bin/{sample.BOARD}", f"bin/cmake-{sample.BOARD}",
                         f"scan-build/{sample.BOARD}"):
                self.assertFalse(t.exists(name), name)
            for name in ("bin/native64/z.o", "scan-build/native64/index.html", "main.c",
                         "Makefile", "riot-app.yaml"):
                self.assertTrue(t.exists(name), name)
        finally:
            t.cleanup()

    def test_failing_command_is_ignored(self):
        t = Tree()
        try:
            result = C.plan_clean(t.app, variables())
            bad = dict(C.rm_entry("/nonexistent-dir/x", t.app, "test", False),
                       argv=["false"])
            result["clean"].insert(0, bad)
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertEqual(C.run(result), 0)
            self.assertIn("failed with exit status 1 (ignored", err.getvalue())
            self.assertFalse(t.exists(f"bin/{sample.BOARD}"))       # the rest ran
        finally:
            t.cleanup()

    def test_dry_run_removes_nothing(self):
        t = Tree()
        try:
            status, out, _ = t.clean("-n")
            self.assertEqual(status, 0)
            self.assertEqual(len(out.split("\n")[:-1]), 5)
            self.assertTrue(t.exists(f"bin/{sample.BOARD}/core/x.o"))
            self.assertTrue(t.exists(f"bin/cmake-{sample.BOARD}/build.ninja"))
        finally:
            t.cleanup()


class ExitTest(unittest.TestCase):
    """A6."""

    def test_outside_the_data(self):
        t = Tree()
        try:
            self.assertEqual(t.clean(BOARD="native64")[0], 3)
            self.assertEqual(t.clean(PKG_SOURCE_LOCAL_CMSIS="/tmp/x")[0], 3)
            self.assertEqual(t.clean(PKG_SOURCE_LOCAL="/tmp/x")[0], 3)
            os.remove(os.path.join(t.app, "riot-app.yaml"))
            status, _, err = t.clean()
            self.assertEqual(status, 3)
            self.assertIn("riot-app.yaml does not exist", err)
            self.assertTrue(t.exists(f"bin/{sample.BOARD}/core/x.o"))
        finally:
            t.cleanup()

    def test_invalid_clean_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.clean.yaml")
            with open(path, "w", encoding="utf-8") as file:
                file.write("schema: 3\nrules: [{section: x}]\n")
            ev = C.CleanEvaluator(C.buildeval.BuildVariables(), tmp)
            with self.assertRaisesRegex(C.ResolveError, "build data only"):
                ev.load(path)


class SafetyTest(unittest.TestCase):
    """S1-S4."""

    def refused(self, t, *args, **values):
        status, out, err = t.clean(*args, **values)
        self.assertEqual(status, C.REFUSED, (out, err))
        self.assertIn("Nothing removed.", err)
        return err

    def assert_nothing_removed(self, t):
        for name in (f"bin/{sample.BOARD}/core/x.o", f"bin/cmake-{sample.BOARD}/build.ninja",
                     f"scan-build/{sample.BOARD}/index.html"):
            self.assertTrue(t.exists(name), name)

    def test_s1_plain_words(self):
        t = Tree()
        try:
            for value in ("scan build", "scan-build/*", "scan-build/$(X)", "'x'",
                          "scan-build/../..", "x;y", ""):
                with self.subTest(value=value):
                    err = self.refused(t, SCANBUILD_OUTPUTDIR=value)
                    self.assertIn("(S1)", err)
            self.assert_nothing_removed(t)
        finally:
            t.cleanup()

    def test_s2_roots(self):
        t = Tree()
        home = os.path.expanduser("~")
        try:
            cases = [{"BINDIRBASE": "/"}, {"BINDIRBASE": home},
                     {"BINDIRBASE": sample.RIOTBASE}, {"BINDIRBASE": os.path.dirname(t.app)},
                     {"BINDIR": t.app}, {"BINDIR": os.path.join(t.app, "src")},
                     {"BINDIR": os.path.join(t.root, "elsewhere")},
                     {"SCANBUILD_OUTPUTDIR": "abc"}, {"SCANBUILD_OUTPUTDIR": "scan-build"},
                     {"SCANBUILD_OUTPUTDIR": "/tmp"}]
            for values in cases:
                with self.subTest(values=values):
                    self.assertIn("(S2", self.refused(t, **values))
            for builddir in ("/", home, t.app, os.path.join(t.root, "out"), sample.RIOTBASE):
                with self.subTest(builddir=builddir):
                    self.assertIn("(S2", self.refused(t, "-B", builddir))
            self.assert_nothing_removed(t)
        finally:
            t.cleanup()

    def test_s2_accepted_roots(self):
        app = os.path.join(sample.RIOTBASE, sample.APPS[HELLO])
        with tempfile.TemporaryDirectory() as tmp:
            for values, builddir in (({}, None), ({"BINDIRBASE": os.path.join(tmp, "b")}, None),
                                     ({}, f"{app}/bin/other"),
                                     ({"BUILD_DIR": os.path.join(tmp, "build")},
                                      os.path.join(tmp, "build", "x")),
                                     ({"PKG_BUILD_OUT_OF_SOURCE": "0"}, None)):
                with self.subTest(values=values, builddir=builddir):
                    result = C.plan_clean(app, variables(**values), builddir)
                    self.assertEqual(C.refusals(result), [])

    def test_roots(self):
        app = os.path.join(sample.RIOTBASE, sample.APPS[HELLO])
        ev = C.evaluate(app, variables())
        self.assertEqual(C.roots(ev.v), [f"{app}/bin", f"{app}/scan-build",
                                         f"{sample.RIOTBASE}/build"])
        ev = C.evaluate(app, variables(BINDIRBASE="/", BUILD_DIR=os.path.expanduser("~")))
        self.assertEqual(C.roots(ev.v), [f"{app}/bin", f"{app}/scan-build"])

    def test_s3_symbolic_link_out_of_a_root(self):
        t = Tree()
        try:
            outside = os.path.join(t.root, "outside")
            victim = t.put("cmsis/precious.c", outside)
            link = os.path.join(t.app, "bin", sample.BOARD, "pkg-build")
            subprocess.run(["rm", "-rf", link], check=True)
            os.symlink(outside, link)
            err = self.refused(t)
            self.assertIn("through a symbolic link (S3)", err)
            self.assertTrue(os.path.isfile(victim))
            self.assert_nothing_removed(t)
            # a link as the path itself is removed, not followed (rm -rf)
            os.remove(link)
            os.symlink(outside, os.path.join(t.app, "bin", f"cmake-{sample.BOARD}-link"))
            status, _, _ = t.clean("-B", os.path.join(t.app, "bin", f"cmake-{sample.BOARD}-link"))
            self.assertEqual(status, 0)
            self.assertTrue(os.path.isfile(victim))
            self.assertFalse(t.exists(f"bin/cmake-{sample.BOARD}-link"))
        finally:
            t.cleanup()

    def test_s4_nothing_removed_on_one_refusal(self):
        t = Tree()
        try:
            # only the last path (the scan-build reports) is refused
            self.refused(t, SCANBUILD_OUTPUTDIR="../x")
            self.assert_nothing_removed(t)
            self.assertTrue(t.exists(f"bin/{sample.BOARD}/pkg-build/cmsis/y.o"))
        finally:
            t.cleanup()

    def test_s4_dry_run_refuses(self):
        t = Tree()
        try:
            status, out, _ = t.clean("-n", BINDIRBASE="/")
            self.assertEqual((status, out), (C.REFUSED, ""))
        finally:
            t.cleanup()


if __name__ == "__main__":
    unittest.main()
