# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""K1-K3: the package step without Make (pkg_prepare.py).

K1 compares the clone commands with those of GNU Make (golden files, no
network); K2 runs the step on a local git repository (no network); K3
(opt-in, network and GNU Make: RIOT_G3_NETWORK=1) prepares the packages of
gnrc_networking with Make and without Make and compares the file trees.
"""

import filecmp
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import pkg_prepare as K  # noqa: E402
import plan as P  # noqa: E402
import sample  # noqa: E402

GIT = shutil.which("git")
PLACEHOLDER = "/nonexistent-g3-build-dir"
GIT_IN_PKG = re.compile(r"git (?:init(?: --quiet)? \S+|-C (\S+) --git-dir=\.git --work-tree=\. "
                        r"(?:sparse-checkout (?:init|set)|remote add|config|fetch --quiet --depth|"
                        r"checkout --quiet [0-9a-f]+ |cat-file -e)[^;\n]*)")


def specs(app_dir: str) -> list:
    plan = P.build_plan(os.path.join(P.RIOTBASE, app_dir), {"BOARD": sample.BOARD,
                                                            "BUILD_DIR": PLACEHOLDER,
                                  "BINDIR": "/nonexistent-g3-bindir"})
    return plan["packages"]


def make_git_commands(text: str) -> dict:
    """The clone commands of each package directory in Make's output (first
    clone only), as word lists."""
    out = {}
    current = None
    for match in GIT_IN_PKG.finditer(text):
        command = match.group(0).strip()
        words = shlex.split(command.replace("2>&1 | cat", ""))
        directory = words[2] if words[1] == "-C" else words[-1]
        if words[1] == "init":
            current = directory
            if directory in out:
                current = None
                continue
            out[directory] = []
        if current == directory:
            out[directory].append(words)
    for words_list in out.values():
        # Make prints the sparse checkout inside `if [ -n "<paths>" ]`: without
        # paths (`sparse-checkout set --` alone) the shell skips both commands
        if ["sparse-checkout", "set", "--"] == words_list[2][5:] if len(words_list) > 2 else False:
            del words_list[1:3]
    return out


class CloneCommandsTest(unittest.TestCase):
    """K1: a package that is missing is cloned with Make's commands."""

    def test_clone_commands_are_makes(self):
        for app, app_dir in sample.APPS.items():
            _, sections = sample.read_golden(sample.golden_path(app))
            make = make_git_commands(sample.section(sections, sample.FRESH))
            self.assertEqual(len(make), 3, app)
            for spec in specs(app_dir):
                with self.subTest(app=app, package=spec["name"]):
                    log = K.prepare(spec, P.RIOTBASE, K.Runner(dry_run=True, log=[], verbose=False))
                    ours = [shlex.split(c.replace("2>&1 | cat", ""))
                            for c in log if c.startswith("git ") and " clean " not in c
                            and " am " not in c and " checkout --quiet -f" not in c
                            and " fetch --quiet \"" not in c and " apply " not in c]
                    ours = [[w.replace(PLACEHOLDER, "@BUILD_DIR@") for w in c] for c in ours]
                    directory = spec["source_dir"].replace(PLACEHOLDER, "@BUILD_DIR@")
                    self.assertEqual(ours, make[directory])


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipIf(GIT is None, "git is not installed")
class LocalPackageTest(unittest.TestCase):
    """K2: fetch, patch, copy and state files on a local repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.upstream = os.path.join(root, "upstream")
        os.makedirs(os.path.join(self.upstream, "mdk"))
        for name in ("mdk/a.h", "mdk/b.h", "other.c"):
            with open(os.path.join(self.upstream, name), "w", encoding="utf-8") as file:
                file.write(f"/* {name} */\n")
        ident = ["-c", "user.email=t@t", "-c", "user.name=t"]
        git("init", "-q", cwd=self.upstream)
        git("add", ".", cwd=self.upstream)
        git(*ident, "commit", "-qm", "v1", cwd=self.upstream)
        self.version = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.upstream,
                                      capture_output=True, text=True, check=True).stdout.strip()
        with open(os.path.join(self.upstream, "mdk/a.h"), "a", encoding="utf-8") as file:
            file.write("/* patched */\n")
        git(*ident, "commit", "-qam", "RIOT patch", cwd=self.upstream)
        self.patches = os.path.join(root, "patches")
        git("format-patch", "-q", "-1", "-o", self.patches, cwd=self.upstream)
        git("checkout", "-q", self.version, cwd=self.upstream)
        self.data = os.path.join(root, "pkg.yaml")
        with open(self.data, "w", encoding="utf-8") as file:
            file.write("data\n")
        self.build = os.path.join(root, "build")
        self.spec = {
            "name": "x", "url": self.upstream, "version": self.version, "license": "MIT",
            "source_dir": os.path.join(self.build, "x"), "sparse_paths": ["mdk/a.h", "mdk/b.h"],
            "patches": sorted(os.path.join(self.patches, p) for p in os.listdir(self.patches)),
            "git_quiet": "--quiet",
            "gitflags": '-c user.email=buildsystem@riot -c user.name="RIOT buildsystem"',
            "gitamflags": "--quiet --no-gpg-sign --ignore-whitespace --whitespace=nowarn",
            "ci": False, "build_dir": self.build, "data": [self.data],
            "copy": {"from": os.path.join(self.build, "x", "mdk"),
                     "to": os.path.join(self.build, "x", "vendor"), "files": ["a.h", "b.h"]},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_step(self):
        return K.prepare(self.spec, "/", K.Runner(log=[], verbose=False))

    def test_prepare_fetch_patch_copy(self):
        log = self.run_step()
        src = self.spec["source_dir"]
        for state in ("downloaded", "patched", "prepared"):
            self.assertTrue(os.path.exists(os.path.join(src, f".pkg-state.git-{state}")), state)
        with open(os.path.join(src, "vendor", "a.h"), encoding="utf-8") as file:
            self.assertIn("patched", file.read())
        self.assertFalse(os.path.exists(os.path.join(src, "other.c")), "sparse checkout")
        self.assertTrue(os.path.exists(os.path.join(self.build, "CACHEDIR.TAG")))
        with open(f"{src}.sparse", encoding="utf-8") as file:
            self.assertEqual(file.read().strip(), "mdk/a.h mdk/b.h")
        self.assertTrue(any(" am " in c for c in log))

    def test_second_run_does_nothing(self):
        self.run_step()
        self.assertEqual(self.run_step(), [])

    def test_changed_patch_or_data_patches_again_without_cloning(self):
        self.run_step()
        time.sleep(0.01)
        os.utime(self.spec["patches"][0])
        log = self.run_step()
        self.assertTrue(any(" am " in c for c in log))
        self.assertFalse(any("git init" in c for c in log))
        os.utime(self.data)
        log = self.run_step()
        self.assertTrue(any("cat-file -e" in c for c in log))

    def test_changed_sparse_paths_clone_again(self):
        self.run_step()
        self.spec["sparse_paths"] = ["mdk/a.h"]
        self.spec["copy"]["files"] = ["a.h"]
        log = self.run_step()
        self.assertTrue(any(c.startswith("git init") for c in log))

    def test_ci_applies_with_git_apply(self):
        self.spec["ci"] = True
        log = self.run_step()
        self.assertTrue(any(" apply --index " in c for c in log))

    def test_failing_command_stops(self):
        self.spec["version"] = "0" * 40
        with self.assertRaises(K.PackageError):
            self.run_step()

    def test_removal_only_inside_build_dir(self):
        self.spec["source_dir"] = self.tmp.name
        with self.assertRaises(K.PackageError):
            self.run_step()
        self.assertTrue(os.path.isdir(self.upstream))


def tree(path: str) -> dict:
    out = {}
    for directory, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            if name.startswith(".pkg-state"):
                continue
            full = os.path.join(directory, name)
            out[os.path.relpath(full, path)] = full
    return out


@unittest.skipUnless(os.environ.get("RIOT_G3_NETWORK") == "1" and shutil.which("make") and GIT,
                     "opt-in: RIOT_G3_NETWORK=1, needs the network and GNU Make")
class SameTreeAsMakeTest(unittest.TestCase):
    """K3: the prepared packages are the same files as Make's."""

    def test_same_files(self):
        app_dir = sample.APPS["gnrc_networking"]
        with tempfile.TemporaryDirectory() as tmp:
            make_dir, ours = os.path.join(tmp, "make"), os.path.join(tmp, "ours")
            subprocess.run(sample.make_argv(app_dir, [f"BUILD_DIR={make_dir}",
                                                      "fetch_nrfx_vendor_headers",
                                                      "pkg-prepare"]),
                           cwd=sample.RIOTBASE, env=sample.environment(), check=True,
                           capture_output=True)
            plan = P.build_plan(os.path.join(P.RIOTBASE, app_dir),
                                {"BOARD": sample.BOARD, "BUILD_DIR": ours,
                                          "BINDIR": os.path.join(tmp, "bin")},
                                lambda spec: K.prepare(spec, P.RIOTBASE, K.Runner(log=[], verbose=False)))
            self.assertEqual(len(plan["packages"]), 3)
            left, right = tree(make_dir), tree(ours)
            self.assertEqual(sorted(left), sorted(right))
            for name in left:
                with self.subTest(name=name):
                    self.assertTrue(filecmp.cmp(left[name], right[name], shallow=False))


if __name__ == "__main__":
    unittest.main()
