#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for step g2c-03-pkg-clean: the root Make target `pkg-clean`
(group 2C) moved to the just recipe `pkg-clean`.

* R1  same output, exit status and effect as `make pkg-clean`;
* R2  the recipe calls no make and reads no Make file;
* R3  `make pkg-clean` is unknown at the root; the welcome text lists it
      under "moved to just";
* R4  no caller runs `make pkg-clean`; the root `distclean` delegates to
      `just pkg-clean` (one definition of the cleaning);
* R5  the root `make distclean` prints the same lines in the same order and
      leaves the same tree as before;
* R6  reachable from every directory: same output and effect everywhere;
* S   safety: nothing outside <repository>/build/pkg is ever deleted.

Real runs happen only in temporary trees (root Makefile, makefiles/, the
justfile and stub Makefiles for doc/ and one application). The Makefile of
the base commit (BASE_COMMIT) is taken from git for the live comparison;
without it those tests are skipped and the recorded output is used.

Run: python3 -m unittest discover -s dist/tools/pkg_clean/tests -v
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
JUSTFILE = os.path.join(RIOTBASE, "justfile")
JUST = shutil.which("just")
MAKE = shutil.which("make")
GIT = shutil.which("git")
TEST_DIR = os.path.relpath(HERE, RIOTBASE)

# Last commit with the Make target (base of migration/g2c-03-pkg-clean).
BASE_COMMIT = "74a0fb9743"

# `make --no-print-directory pkg-clean` at the root of BASE_COMMIT
# (GNU Make 4.3, 2026-11-22): exit 0, nothing on stderr.
GOLDEN_STDOUT = "Cleaning all package sources\nrm -rf build/pkg\n"

sys.path.insert(0, os.path.join(RIOTBASE, "dist", "tools", "task_layer", "tests"))
from test_justfile import MAKE_CALL, recipe_lines  # noqa: E402  pylint: disable=wrong-import-position


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def dump():
    result = run([JUST, "--justfile", JUSTFILE, "--dump", "--dump-format", "json"])
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def base_makefile():
    """Root Makefile of BASE_COMMIT, or None if git or the commit is missing."""
    if GIT is None:
        return None
    result = run([GIT, "-C", RIOTBASE, "show", f"{BASE_COMMIT}:Makefile"])
    return result.stdout if result.returncode == 0 else None


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    if mode is not None:
        os.chmod(path, mode)


STUB_MAKEFILE = "clean:\n\t@echo {name}-clean\ndistclean:\n\t@echo {name}-distclean\n"


class Tree:
    """A temporary RIOT tree with package sources and decoys around them."""

    def __init__(self, makefile=None):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.outside = os.path.join(self.tmp.name, "outside")
        self.root = os.path.join(self.tmp.name, "riot")
        os.makedirs(self.root)
        shutil.copy(JUSTFILE, self.root)
        if makefile is None:
            shutil.copy(os.path.join(RIOTBASE, "Makefile"), self.root)
        else:
            write(os.path.join(self.root, "Makefile"), makefile)
        shutil.copytree(os.path.join(RIOTBASE, "makefiles"), os.path.join(self.root, "makefiles"))
        for name in ("bootloaders", "fuzzing", "tests"):  # searched by app_dirs.inc.mk
            os.makedirs(os.path.join(self.root, name))
        for name in ("doc/doxygen", "doc/starlight", "examples/app", "dist/tools/tool"):
            write(os.path.join(self.root, name, "Makefile"),
                  STUB_MAKEFILE.format(name=os.path.basename(name)))
        self.files = {
            # removed
            "build/pkg/foo/src/a.c": False, "build/pkg/bar/.git/HEAD": False,
            "build/pkg/.hidden": False,
            # kept
            "build/other/keep": True, "build/pkg.keep": True,
            "examples/app/build/pkg/decoy": True, "examples/app/bin/x/pkg/decoy": True,
        }
        for name in self.files:
            write(os.path.join(self.root, name), name)
        write(os.path.join(self.outside, "build", "pkg", "decoy"), "outside")
        write(os.path.join(self.outside, "pkg", "decoy"), "outside")

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def survivors(self):
        """Every file below the temporary directory (relative) except the
        copied Makefiles, makefiles/ and the justfile."""
        found = set()
        for top, _dirs, files in os.walk(self.tmp.name):
            for name in files:
                rel = os.path.relpath(os.path.join(top, name), self.tmp.name)
                if name not in ("Makefile", "justfile") and not rel.startswith("riot/makefiles/"):
                    found.add(rel)
        return found

    def expected_survivors(self):
        kept = {os.path.join("riot", n) for n, keep in self.files.items() if keep}
        return kept | {"outside/build/pkg/decoy", "outside/pkg/decoy"}

    def cleanup(self):
        for top, dirs, _files in os.walk(self.tmp.name):
            for name in dirs:
                os.chmod(os.path.join(top, name), 0o755)
        self.tmp.cleanup()


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("MAKE", "MFLAGS", "BUILD_DIR", "PKGDIRBASE", "RIOTBASE"))}
    env.update(LC_ALL="C", CC_NOCOLOR="1", **extra)
    return env


def just_pkg_clean(tree, cwd=None, args=("pkg-clean",), env=None):
    return run([JUST, *args], cwd=cwd or tree.root, env=env or clean_env())


@unittest.skipIf(JUST is None, "just is not installed")
class RecipeContractTest(unittest.TestCase):
    """R1, R2, S: what the recipes are. `pkg-clean` runs the private steps
    `_pkg-clean` with the repository directory and mode `echo`; the root
    `make distclean` runs the same steps with its CURDIR and mode."""

    @classmethod
    def setUpClass(cls):
        recipes = dump()["recipes"]
        cls.recipe = recipes["pkg-clean"]
        cls.steps = recipes["_pkg-clean"]
        cls.lines = recipe_lines(cls.steps)

    def test_public_without_parameters(self):
        self.assertFalse(self.recipe["private"])
        self.assertEqual(self.recipe["parameters"], [])
        self.assertEqual(self.recipe["body"], [])
        self.assertNotIn("no-cd", self.recipe["attributes"])

    def test_runs_the_steps_in_the_repository_root(self):
        self.assertEqual(self.recipe["dependencies"], [{
            "arguments": [["call", "justfile_directory"], "echo"],
            "recipe": "_pkg-clean", "star": None}])

    def test_steps_are_private_with_directory_and_mode(self):
        self.assertTrue(self.steps["private"])
        self.assertEqual([p["name"] for p in self.steps["parameters"]], ["dir", "mode"])
        self.assertTrue(all(p["default"] is None for p in self.steps["parameters"]))
        self.assertTrue(self.steps["shebang"])
        self.assertEqual(self.lines[:2], ["#!/bin/sh", "set -e"])

    def test_one_fixed_directory_below_dir(self):
        self.assertIn('cd "$dir"', self.lines)
        self.assertIn('msg="Cleaning all package sources" pkg=build/pkg', self.lines)
        removals = [line for line in self.lines if "rm -rf" in line and "echo" not in line]
        self.assertEqual(removals, ['rm -rf "$pkg"'])
        # validation and `cd` come before the removal
        self.assertLess(self.lines.index('cd "$dir"'), self.lines.index('rm -rf "$pkg"'))

    def test_no_make_and_no_make_file(self):
        for line in recipe_lines(self.recipe) + self.lines:
            with self.subTest(line=line):
                self.assertIsNone(MAKE_CALL.search(line))
                self.assertNotRegex(line, r"Makefile|\.mk\b|\$\(")

    def test_dry_run_shows_the_script(self):
        result = run([JUST, "--dry-run", "pkg-clean"], cwd=RIOTBASE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"dir='{RIOTBASE}' mode='echo'\n", result.stderr)


@unittest.skipIf(JUST is None, "just is not installed")
class EffectTest(unittest.TestCase):
    """R1: output, exit status and effect in a temporary tree."""

    def setUp(self):
        self.tree = Tree()
        self.addCleanup(self.tree.cleanup)

    def test_removes_exactly_build_pkg(self):
        result = just_pkg_clean(self.tree)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, GOLDEN_STDOUT, ""))
        self.assertFalse(os.path.lexists(self.tree.path("build", "pkg")))
        self.assertEqual(self.tree.survivors(), self.tree.expected_survivors())

    def test_idempotent(self):
        just_pkg_clean(self.tree)
        result = just_pkg_clean(self.tree)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, GOLDEN_STDOUT, ""))
        self.assertEqual(self.tree.survivors(), self.tree.expected_survivors())

    @unittest.skipIf(os.geteuid() == 0, "root may remove read-only entries")
    def test_failure_is_reported(self):
        os.chmod(self.tree.path("build", "pkg", "foo", "src"), 0o555)
        result = just_pkg_clean(self.tree)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, GOLDEN_STDOUT)
        self.assertIn("rm: cannot remove 'build/pkg/foo/src/a.c': Permission denied", result.stderr)


@unittest.skipIf(JUST is None or MAKE is None, "just or make is not installed")
class MakeParityTest(unittest.TestCase):
    """R1: `just pkg-clean` = `make pkg-clean` of the base commit."""

    @classmethod
    def setUpClass(cls):
        cls.old = base_makefile()
        if cls.old is None:
            raise unittest.SkipTest(f"base commit {BASE_COMMIT} not available")

    def outcome(self, command, prepare=None):
        tree = Tree(makefile=self.old)
        self.addCleanup(tree.cleanup)
        if prepare:
            prepare(tree)
        result = run(command, cwd=tree.root, env=clean_env())
        return result, tree.survivors()

    def test_same_output_and_effect(self):
        make, make_files = self.outcome([MAKE, "--no-print-directory", "pkg-clean"])
        just, just_files = self.outcome([JUST, "pkg-clean"])
        self.assertEqual(make.stdout, GOLDEN_STDOUT)
        self.assertEqual((just.returncode, just.stdout, just.stderr),
                         (make.returncode, make.stdout, make.stderr))
        self.assertEqual(just_files, make_files)

    def test_overrides_are_ignored_by_both(self):
        def env_and_args(tool):
            return [tool, "BUILD_DIR=../outside", "PKGDIRBASE=../outside/pkg"]
        make, make_files = self.outcome(env_and_args(MAKE)[:1] + ["--no-print-directory", "pkg-clean"]
                                        + env_and_args(MAKE)[1:])
        just, just_files = self.outcome([JUST, "pkg-clean"])
        self.assertEqual(make.stdout, just.stdout)
        self.assertEqual(just_files, make_files)
        self.assertIn("outside/pkg/decoy", make_files)

    @unittest.skipIf(os.geteuid() == 0, "root may remove read-only entries")
    def test_same_failure_output(self):
        def lock(tree):
            os.chmod(tree.path("build", "pkg", "foo", "src"), 0o555)
        make, make_files = self.outcome([MAKE, "--no-print-directory", "pkg-clean"], lock)
        just, just_files = self.outcome([JUST, "pkg-clean"], lock)
        self.assertEqual(just.stdout, make.stdout)
        rm_line = [line for line in make.stderr.splitlines() if line.startswith("rm:")]
        self.assertEqual([line for line in just.stderr.splitlines() if line.startswith("rm:")], rm_line)
        # Documented difference: Make exits 2, just passes on rm's status 1.
        self.assertEqual((make.returncode, just.returncode), (2, 1))
        self.assertEqual(just_files, make_files)


@unittest.skipIf(JUST is None, "just is not installed")
class NoMakeTest(unittest.TestCase):
    """R2: a real run with a `make` on PATH that only records being called."""

    def test_make_is_never_started(self):
        tree = Tree()
        self.addCleanup(tree.cleanup)
        stub_dir = os.path.join(tree.tmp.name, "stubs")
        marker = os.path.join(tree.tmp.name, "make-was-called")
        for name in ("make", "gmake"):
            write(os.path.join(stub_dir, name), f"#!/bin/sh\ntouch '{marker}'\nexit 99\n", 0o755)
        env = clean_env(PATH=stub_dir + os.pathsep + os.environ["PATH"])
        result = just_pkg_clean(tree, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(os.path.lexists(tree.path("build", "pkg")))

    def test_detector_samples(self):
        self.assertIsNotNone(MAKE_CALL.search('make -C "$root" pkg-clean'))
        self.assertIsNotNone(MAKE_CALL.search('cd x && make pkg-clean'))
        self.assertIsNone(MAKE_CALL.search('rm -rf "$dir"'))
        self.assertIsNone(MAKE_CALL.search('echo "remake"'))


class MakefileTest(unittest.TestCase):
    """R3, R4: the root Makefile no longer has the target and delegates."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(RIOTBASE, "Makefile"), encoding="utf-8") as file:
            cls.text = file.read()

    def test_no_rule_and_no_phony_entry(self):
        self.assertIsNone(re.search(r"^pkg-clean\s*:", self.text, re.M))
        phony = " ".join(re.findall(r"^\.PHONY:(.*)$", self.text, re.M)).split()
        self.assertNotIn("pkg-clean", phony)

    def test_cleaning_is_defined_only_in_the_justfile(self):
        self.assertNotIn("build/pkg", self.text)
        self.assertNotIn("Cleaning all package sources", self.text)
        prerequisites = re.search(r"^distclean:(.*)$", self.text, re.M).group(1).split()
        self.assertEqual(prerequisites[:2], ["docclean", "_pkg-clean"])
        rule = re.search(r"^_pkg-clean:\n((?:\t.*\n)+)", self.text, re.M).group(1)
        self.assertEqual(rule, "\t$(if $(filter dry-run,$(_pkg_clean_mode)),"
                               "$(call _pkg_clean_dry_run,1),@$(_pkg_clean_run))\n"
                               "\t$(call _pkg_clean_dry_run,2)\n")
        run_line = re.search(r"^_pkg_clean_run = (.*)$", self.text, re.M).group(1)
        self.assertEqual(run_line, '"$(JUST)" --justfile "$(_riot_root)justfile" '
                                   '_pkg-clean "$(CURDIR)" $(_pkg_clean_mode)')
        self.assertEqual(len(re.findall(r"\brm\b", self.text)), 0)

    def test_welcome_text_lists_it_under_just(self):
        before, after = self.text.split("moved to just (run 'just --list')", 1)
        self.assertIn("pkg-clean", after.splitlines()[1].split('"')[1].split())
        self.assertNotRegex(before, r'@echo ".*\bpkg-clean\b')

    @unittest.skipIf(MAKE is None, "make is not installed")
    def test_make_treats_it_as_unknown(self):
        # A real run, in a temporary tree with this Makefile.
        tree = Tree()
        self.addCleanup(tree.cleanup)
        result = run([MAKE, "--no-print-directory", "pkg-clean"], cwd=tree.root, env=clean_env())
        self.assertIn('unrecognized target "pkg-clean"', result.stdout)
        self.assertNotIn("Cleaning all package sources", result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(os.path.exists(tree.path("build", "pkg", ".hidden")))


@unittest.skipIf(GIT is None, "git is not installed")
class CallerTest(unittest.TestCase):
    """R4: nobody runs `make pkg-clean` any more."""

    PATTERN = re.compile(r"(\bmake\b|\$\(MAKE\))[^\n]*\bpkg-clean\b")

    def test_no_caller_of_the_make_target(self):
        result = run([GIT, "-C", RIOTBASE, "grep", "-n", "-I", "-P", r"\bpkg-clean\b", "--",
                      ".", ":!release-notes.txt", f":!{TEST_DIR}", ":!dist/tools/task_layer/README.md"])
        if result.returncode not in (0, 1):
            self.skipTest(result.stderr)
        hits = [line for line in result.stdout.splitlines() if self.PATTERN.search(line)]
        self.assertEqual(hits, [])

    def test_detector_samples(self):
        self.assertIsNotNone(self.PATTERN.search("    make pkg-clean"))
        self.assertIsNotNone(self.PATTERN.search('"$(MAKE)" -C $(RIOTBASE) pkg-clean'))
        self.assertIsNone(self.PATTERN.search("just pkg-clean"))
        self.assertIsNone(self.PATTERN.search("make clean-pkg"))


@unittest.skipIf(JUST is None or MAKE is None, "just or make is not installed")
class DistcleanTest(unittest.TestCase):
    """R5: the root `make distclean` behaves as before."""

    # Output of `make --no-print-directory distclean` in the temporary tree
    # (stub Makefiles for doc/ and one application) on BASE_COMMIT.
    GOLDEN = ['"{make}" -BC doc/doxygen clean', "doxygen-clean",
              '"{make}" -C doc/starlight clean', "starlight-clean",
              "Cleaning all package sources", "rm -rf build/pkg",
              '"{make}" -C examples/app distclean', "app-distclean",
              '"{make}" -C dist/tools/tool distclean', "tool-distclean",
              "Cleaned everything."]

    @classmethod
    def setUpClass(cls):
        cls.golden = [line.format(make=MAKE) for line in cls.GOLDEN]

    def distclean(self, makefile=None, args=(), print_directory=False):
        tree = Tree(makefile=makefile)
        self.addCleanup(tree.cleanup)
        options = [] if print_directory else ["--no-print-directory"]
        result = run([MAKE, *options, "distclean", *args], cwd=tree.root, env=clean_env())
        result.stdout = result.stdout.replace(tree.tmp.name, "<tmp>")
        return result, tree

    def test_same_lines_order_and_effect_as_recorded(self):
        result, tree = self.distclean()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), self.golden)
        self.assertEqual(tree.survivors(), tree.expected_survivors())

    def test_same_as_base_commit(self):
        old = base_makefile()
        if old is None:
            self.skipTest(f"base commit {BASE_COMMIT} not available")
        new, new_tree = self.distclean()
        before, old_tree = self.distclean(makefile=old)
        self.assertEqual(before.stdout.splitlines(), self.golden)
        self.assertEqual((new.returncode, new.stdout, new.stderr),
                         (before.returncode, before.stdout, before.stderr))
        self.assertEqual(new_tree.survivors(), old_tree.survivors())

    FLAGS = ([], ["-s"], ["-n"], ["-ns"], ["-k"], ["-sk"], ["-q"], ["-n", "-k"], ["--silent"],
             ["--just-print"])

    def test_options_as_on_the_base_commit(self):
        """-s stays silent, -n prints the same commands and changes nothing,
        -k, -q as before: stdout, stderr, exit status and effect."""
        old = base_makefile()
        if old is None:
            self.skipTest(f"base commit {BASE_COMMIT} not available")
        for flags, print_directory in [(f, False) for f in self.FLAGS] + [([], True), (["-s"], True)]:
            with self.subTest(flags=flags, print_directory=print_directory):
                new, new_tree = self.distclean(args=flags, print_directory=print_directory)
                before, old_tree = self.distclean(makefile=old, args=flags, print_directory=print_directory)
                self.assertEqual((new.returncode, new.stdout, new.stderr),
                                 (before.returncode, before.stdout, before.stderr))
                self.assertEqual(new_tree.survivors(), old_tree.survivors())

    def test_silent_and_dry_run_as_recorded(self):
        silent, tree = self.distclean(args=["-s"])
        self.assertEqual(silent.stdout.splitlines(),
                         [line for line in self.golden if not line.startswith(('"', "rm "))])
        self.assertFalse(os.path.lexists(tree.path("build", "pkg")))
        dry, tree = self.distclean(args=["-n"])
        self.assertIn('echo "Cleaning all package sources"\nrm -rf build/pkg\n', dry.stdout)
        self.assertNotIn("just", dry.stdout)
        self.assertEqual(tree.survivors(), tree.expected_survivors()
                         | {os.path.join("riot", n) for n, keep in tree.files.items() if not keep})

    def from_other_directory(self, makefile, flags, other_is_riot):
        """`make -f <tree>/Makefile distclean` run in <outside>; with
        other_is_riot, <outside> is a second tree without a justfile."""
        tree = Tree(makefile=makefile)
        self.addCleanup(tree.cleanup)
        if other_is_riot:
            other = Tree(makefile=makefile)
            self.addCleanup(other.cleanup)
            os.remove(other.path("justfile"))
            cwd = other.root
        else:
            other, cwd = None, tree.outside
        result = run([MAKE, "--no-print-directory", *flags, "-f", tree.path("Makefile"), "distclean"],
                     cwd=cwd, env=clean_env())
        replace = [(tree.tmp.name, "<tree>")] + ([(other.tmp.name, "<other>")] if other else [])
        out, err = result.stdout, result.stderr
        for path, name in replace:
            out, err = out.replace(path, name), err.replace(path, name)
        # Without makefiles/ in CURDIR Make prints the welcome text, whose
        # lists of targets changed on purpose (R3); everything else must not.
        out = re.sub(r"^ (clean distclean docclean|doc generate-features)\b.*$", r" \1 <list>", out,
                     flags=re.M)
        files = (tree.survivors(), other.survivors() if other else None)
        return (result.returncode, out, err), files

    def test_makefile_from_another_directory_as_before(self):
        """CURDIR is cleaned, as Make did; the justfile is the one next to
        the Makefile. Without -k Make already failed in `docclean`."""
        old = base_makefile()
        if old is None:
            self.skipTest(f"base commit {BASE_COMMIT} not available")
        for flags in ([], ["-k"], ["-s", "-k"], ["-n", "-k"]):
            for other_is_riot in (False, True):
                with self.subTest(flags=flags, other_is_riot=other_is_riot):
                    new = self.from_other_directory(None, flags, other_is_riot)
                    before = self.from_other_directory(old, flags, other_is_riot)
                    self.assertEqual(new, before)

    def test_makefile_from_another_directory_cleans_curdir(self):
        (status, _out, _err), (tree_files, _) = self.from_other_directory(None, ["-k"], False)
        self.assertEqual(status, 2)  # docclean fails: no doc/ in CURDIR
        self.assertNotIn("outside/build/pkg/decoy", tree_files)
        self.assertIn("riot/build/pkg/.hidden", tree_files)
        _result, (_tree, other_files) = self.from_other_directory(None, [], True)
        self.assertNotIn("riot/build/pkg/.hidden", other_files)

    def test_touch_mode_difference(self):
        """Documented difference: `make -t distclean` touched a file named
        `pkg-clean` (the old target was not .PHONY); `_pkg-clean` is phony."""
        result, tree = self.distclean(args=["-t"])
        self.assertNotIn("touch pkg-clean", result.stdout)
        self.assertFalse(os.path.exists(tree.path("pkg-clean")))
        self.assertTrue(os.path.exists(tree.path("build", "pkg", ".hidden")))

    def test_fails_without_just(self):
        result, tree = self.distclean(args=["JUST=/nonexistent/just"])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Cleaned everything.", result.stdout)
        self.assertTrue(os.path.exists(tree.path("build", "pkg", ".hidden")))


@unittest.skipIf(JUST is None, "just is not installed")
class ReachabilityTest(unittest.TestCase):
    """R6 (C1-C3): repository-global, so reachable from every directory.
    From each directory: same output, exit 0, only <root>/build/pkg removed
    (a build/pkg below the calling directory stays)."""

    DIRECTORIES = ("examples/app", "examples/app/build", "doc/doxygen", "makefiles", "build/other")

    def test_same_result_from_every_directory(self):
        for directory in self.DIRECTORIES:
            with self.subTest(directory=directory):
                tree = Tree()
                self.addCleanup(tree.cleanup)
                result = just_pkg_clean(tree, cwd=tree.path(directory))
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, GOLDEN_STDOUT, ""))
                self.assertEqual(tree.survivors(), tree.expected_survivors())

    def test_same_dry_run_command_in_the_repository(self):
        commands = set()
        for directory in ("", "examples/basic/hello-world", "tests/sys/shell", "boards/nrf52840dk", "sys"):
            result = run([JUST, "--dry-run", "pkg-clean"], cwd=os.path.join(RIOTBASE, directory))
            self.assertEqual(result.returncode, 0, result.stderr)
            commands.add(result.stderr)
        self.assertEqual(len(commands), 1)


@unittest.skipIf(JUST is None, "just is not installed")
class SafetyTest(unittest.TestCase):
    """S: no input can make the recipe delete outside <root>/build/pkg."""

    def setUp(self):
        self.tree = Tree()
        self.addCleanup(self.tree.cleanup)

    def assert_untouched(self):
        self.assertTrue(os.path.exists(self.tree.path("build", "pkg", ".hidden")))
        self.assertEqual(self.tree.survivors(), self.tree.expected_survivors()
                         | {os.path.join("riot", n) for n, keep in self.tree.files.items() if not keep})

    def test_arguments_are_refused(self):
        for args in (["pkg-clean", "/"], ["pkg-clean", "../outside"], ["pkg-clean", "dir=/"]):
            with self.subTest(args=args):
                result = just_pkg_clean(self.tree, args=args)
                self.assertNotEqual(result.returncode, 0)
                self.assert_untouched()

    def test_variable_overrides_are_refused(self):
        for args in (["BUILD_DIR=../outside", "pkg-clean"], ["PKGDIRBASE=../outside/pkg", "pkg-clean"],
                     ["dir=..", "pkg-clean"], ["--set", "PKGDIRBASE", "/", "pkg-clean"]):
            with self.subTest(args=args):
                result = just_pkg_clean(self.tree, args=args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not present in justfile", result.stderr)
                self.assert_untouched()

    def test_environment_is_ignored(self):
        env = clean_env(BUILD_DIR=os.path.join(self.tree.outside, "build"),
                        PKGDIRBASE=os.path.join(self.tree.outside, "pkg"), dir="/")
        result = just_pkg_clean(self.tree, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree.survivors(), self.tree.expected_survivors())

    def test_working_directory_option_is_ignored(self):
        result = run([JUST, "--justfile", self.tree.path("justfile"),
                      "--working-directory", self.tree.outside, "pkg-clean"],
                     cwd=self.tree.outside, env=clean_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.tree.survivors(), self.tree.expected_survivors())

    def test_symlinked_pkg_directory_only_loses_the_link(self):
        shutil.rmtree(self.tree.path("build", "pkg"))
        os.symlink(os.path.join(self.tree.outside, "pkg"), self.tree.path("build", "pkg"))
        result = just_pkg_clean(self.tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.tree.path("build", "pkg")))
        self.assertTrue(os.path.exists(os.path.join(self.tree.outside, "pkg", "decoy")))

    def test_stops_if_the_directory_is_missing(self):
        # `set -e`: a failing `cd` must not fall through to `rm` in the
        # working directory, which here has a build/pkg.
        result = run([JUST, "--justfile", self.tree.path("justfile"), "--working-directory",
                      self.tree.outside, "_pkg-clean", "/nonexistent/riot", "echo"],
                     cwd=self.tree.outside, env=clean_env())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Cleaning", result.stdout)
        self.assert_untouched()

    def test_steps_refuse_a_relative_directory(self):
        for directory in ("", ".", "..", "build", "-rf", "~"):
            with self.subTest(directory=directory):
                result = just_pkg_clean(self.tree, cwd=self.tree.path("examples", "app"),
                                        args=("_pkg-clean", directory, "echo"))
                self.assertEqual(result.returncode, 1)
                self.assertIn("not an absolute directory", result.stderr)
                self.assert_untouched()

    def test_steps_refuse_an_unknown_mode(self):
        for mode in ("", "quiet", "rm", "echo; rm -rf /"):
            with self.subTest(mode=mode):
                result = just_pkg_clean(self.tree, args=("_pkg-clean", self.tree.root, mode))
                self.assertEqual(result.returncode, 1)
                self.assertIn("unknown mode", result.stderr)
                self.assert_untouched()

    def test_steps_remove_only_dir_build_pkg(self):
        for mode, stdout in (("echo", GOLDEN_STDOUT), ("silent", "Cleaning all package sources\n")):
            with self.subTest(mode=mode):
                tree = Tree()
                self.addCleanup(tree.cleanup)
                result = just_pkg_clean(tree, args=("_pkg-clean", tree.outside, mode))
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, stdout, ""))
                self.assertEqual(tree.survivors(), (tree.expected_survivors()
                                 - {"outside/build/pkg/decoy"})
                                 | {os.path.join("riot", n) for n, keep in tree.files.items() if not keep})

    def test_dry_run_mode_changes_nothing(self):
        result = just_pkg_clean(self.tree, args=("_pkg-clean", self.tree.root, "dry-run"))
        self.assertEqual((result.returncode, result.stdout),
                         (0, 'echo "Cleaning all package sources"\nrm -rf build/pkg\n'))
        self.assert_untouched()


class RegisterTest(unittest.TestCase):
    """The step is registered with this test directory."""

    def test_step_is_registered(self):
        try:
            import yaml  # pylint: disable=import-outside-toplevel
        except ImportError:
            self.skipTest("PyYAML is not installed")
        with open(os.path.join(RIOTBASE, "dist", "tools", "migration", "steps.yaml"),
                  encoding="utf-8") as file:
            steps = {step["id"]: step for step in yaml.safe_load(file)["steps"]}
        step = steps["g2c-03-pkg-clean"]
        self.assertEqual(step["group"], "2C")
        self.assertEqual(step["targets"], [{"name": "pkg-clean", "now": "just pkg-clean", "hardware": False}])
        self.assertIn(TEST_DIR, step["tests"])


if __name__ == "__main__":
    unittest.main()
