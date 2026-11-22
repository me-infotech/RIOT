#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""S1-S5: the safety rules of `clean` (dist/tools/clean/README.md), extended
to the paths distclean removes in addition (package sources, BINDIRBASE).

S1 a path is one plain word without `..`: also BINDIRBASE and PKGDIRBASE
S2 below a root: <app>/bin, BINDIRBASE, <app>/scan-build, BUILD_DIR and,
   for distclean, PKGDIRBASE; `/`, HOME, RIOTBASE, the application
   directory and their parents are never roots
S3 no symbolic link below a root leads out of it (package sources too)
S4 every path is checked before anything is removed (one refusal: nothing
   removed; `-n` refuses as well)
S5 BINDIRBASE itself (Makefile.include:626) is removed only when it is a
   root (S2) and not a directory directly below `/`
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# pylint: disable=wrong-import-position
import dsample as D  # noqa: E402
import clean as C  # noqa: E402
from dsample import Tree, variables  # noqa: E402


class SafetyTest(unittest.TestCase):
    """S1-S5."""

    def refused(self, t, *args, real=False, **values):
        """Refused with exit 4. Dry run (-n, which refuses as well) unless
        real: a value that names a system or home directory never reaches a
        real run, even if a rule were broken."""
        status, out, err = t.distclean(*(args if real else ("-n",) + args), **values)
        self.assertEqual(status, C.REFUSED, (out, err))
        self.assertIn("Nothing removed.", err)
        return err

    def test_s1_plain_words(self):
        t = Tree()
        try:
            for name in ("BINDIRBASE", "PKGDIRBASE"):
                for value in ("a b", "x/*", "x/$(X)", "'x'", "x;y"):
                    with self.subTest(name=name, value=value):
                        self.assertIn("(S1)", self.refused(t, **{name: os.path.join(
                            t.root, value)}))
            t.assert_untouched(self)
        finally:
            t.cleanup()

    def test_s2_roots(self):
        t = Tree()
        home = os.path.expanduser("~")
        try:
            cases = [{"BINDIRBASE": "/"}, {"BINDIRBASE": home}, {"BINDIRBASE": D.RIOTBASE},
                     {"BINDIRBASE": t.app}, {"BINDIRBASE": t.root},
                     {"PKGDIRBASE": "/"}, {"PKGDIRBASE": home}, {"PKGDIRBASE": D.RIOTBASE},
                     {"PKGDIRBASE": t.app}, {"PKGDIRBASE": t.root},
                     {"BUILD_DIR": home, "PKGDIRBASE": home}]
            for values in cases:
                with self.subTest(values=values):
                    self.assertIn("(S2", self.refused(t, **values))
            for builddir in ("/", home, t.app, os.path.join(t.root, "out"), D.RIOTBASE):
                with self.subTest(builddir=builddir):
                    self.assertIn("(S2", self.refused(t, "-B", builddir))
            t.assert_untouched(self)
        finally:
            t.cleanup()

    def test_s2_accepted_roots(self):
        app = os.path.join(D.RIOTBASE, D.APPS["hello-world"])
        tmp = os.path.join(os.path.dirname(app), "g2c2-not-created")
        for values in ({}, {"BINDIRBASE": f"{tmp}/b"}, {"PKGDIRBASE": f"{tmp}/pkg"},
                       {"BUILD_DIR": f"{tmp}/build"}, {"BINDIRBASE": f"{app}/bin/sub"},
                       {"PKG_BUILD_OUT_OF_SOURCE": "0"}):
            with self.subTest(values=values):
                result = C.plan_distclean(app, variables(**values))
                self.assertEqual(C.refusals(result), [])

    def test_s3_symbolic_link_out_of_a_root(self):
        t = Tree()
        try:
            outside = os.path.join(t.root, "outside")
            victim = t.put("cmsis/precious.c", outside)
            moved = os.path.join(t.root, "pkg-moved")
            os.rename(os.path.join(t.build, "pkg"), moved)
            os.symlink(outside, os.path.join(t.build, "pkg"))
            err = self.refused(t, real=True)
            self.assertIn("through a symbolic link (S3)", err)
            self.assertTrue(os.path.isfile(victim))
            os.remove(os.path.join(t.build, "pkg"))
            os.rename(moved, os.path.join(t.build, "pkg"))
            t.assert_untouched(self)
            # BINDIRBASE as a link is removed, not followed (rm -rf)
            link = os.path.join(t.root, "bin-link")
            os.symlink(outside, link)
            status, _, err = t.distclean(BINDIRBASE=link)
            self.assertEqual(status, 0, err)
            self.assertTrue(os.path.isfile(victim))
            self.assertFalse(os.path.lexists(link))
        finally:
            t.cleanup()

    def test_s4_nothing_removed_on_one_refusal(self):
        t = Tree()
        try:
            # only the last path (BINDIRBASE) is refused
            self.refused(t, BINDIRBASE="/g2c2-top-level", real=True)
            t.assert_untouched(self)
            status, out, _ = t.distclean("-n", PKGDIRBASE="/")
            self.assertEqual((status, out), (C.REFUSED, ""))
            t.assert_untouched(self)
        finally:
            t.cleanup()

    def test_s5_bindirbase_as_a_whole(self):
        t = Tree()
        try:
            for value in ("/g2c2-top-level", "/usr", "/opt"):
                with self.subTest(value=value):
                    err = self.refused(t, BINDIRBASE=value)
                    self.assertIn(f"{value}: a directory directly below / is never removed "
                                  "as a whole (S5)", err)
            t.assert_untouched(self)
            # accepted: <app>/bin (default), below BUILD_DIR, two levels below /
            for whole in (f"{t.app}/bin", f"{t.build}/bins", f"{t.root}/elsewhere"):
                with self.subTest(whole=whole):
                    self.assertEqual(C.whole_root_problem(whole, [whole]), "")
            self.assertIn("(S2", C.whole_root_problem(t.app, [f"{t.app}/bin"]))
        finally:
            t.cleanup()


if __name__ == "__main__":
    unittest.main()
