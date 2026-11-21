#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for the task layer: the root justfile and its callers.

They check the rules of the migration of the group-1 targets
`print-versions` and `generate-features` from the root Makefile to just:

* R1  the recipes exist and run the same command Make ran before;
* R2  no recipe calls make;
* R3  the targets are no longer Make targets;
* R4  every caller uses just (CI check, docs, generated headers);
* R5  the CI check reacts correctly to success, failure and a stale file.

Nothing is built and no repository file is changed: just is asked for its
parsed justfile (`--dump`) and for the command it would run (`--dry-run`);
the CI check runs in a temporary copy with a stub `just`.

Run: python3 -m unittest discover -s dist/tools/task_layer/tests -v
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
JUSTFILE = os.path.join(RIOTBASE, "justfile")
JUST = shutil.which("just")

MIGRATED = {
    "print-versions": "./dist/tools/ci/print_toolchain_versions.sh",
    "generate-features": "./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml "
                         "--output-makefile makefiles/features_existing.inc.mk",
}

MAKE_CALL = re.compile(r"(^|[\s;&|@(`])(\$\(MAKE\)|\$\{MAKE\}|g?make)(\s|$)")


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def dump(justfile):
    result = run([JUST, "--justfile", justfile, "--dump", "--dump-format", "json"])
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def recipe_lines(recipe):
    """Return the literal text of each body line (interpolations left out)."""
    return ["".join(part for part in line if isinstance(part, str)) for line in recipe["body"]]


def recipes_calling_make(parsed):
    return sorted(name for name, recipe in parsed["recipes"].items()
                  if any(MAKE_CALL.search(line) for line in recipe_lines(recipe)))


def write_executable(path, text):
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


@unittest.skipIf(JUST is None, "just is not installed")
class JustfileContractTest(unittest.TestCase):
    """R1, R2: what the justfile contains."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = dump(JUSTFILE)

    def test_migrated_targets_are_public_recipes(self):
        # Later steps add recipes (e.g. `doc`, `list-ttys`,
        # `generate-config-data`); that every public recipe is registered
        # with tests is checked by dist/tools/migration/tests (O2).
        public = {n for n, r in self.parsed["recipes"].items() if not r["private"]}
        self.assertLessEqual(set(MIGRATED), public)

    def test_recipes_run_with_posix_sh_like_make(self):
        self.assertEqual(self.parsed["settings"]["shell"],
                         {"command": "/bin/sh", "arguments": ["-c"]})

    def test_recipe_runs_the_command_make_ran(self):
        for target, command in MIGRATED.items():
            with self.subTest(target=target):
                result = run([JUST, "--justfile", JUSTFILE, "--dry-run", target])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr.strip(), command)

    def test_recipes_have_no_dependencies_or_parameters(self):
        for target in MIGRATED:
            with self.subTest(target=target):
                recipe = self.parsed["recipes"][target]
                self.assertEqual(recipe["dependencies"], [])
                self.assertEqual(recipe["parameters"], [])

    def test_no_recipe_calls_make(self):
        self.assertEqual(recipes_calling_make(self.parsed), [])


@unittest.skipIf(JUST is None, "just is not installed")
class MakeCallDetectorTest(unittest.TestCase):
    """The detector used for R2 must find what it is meant to find."""

    def check(self, body, expected):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "justfile")
            with open(path, "w", encoding="utf-8") as file:
                file.write("r:\n" + textwrap.indent(body, "    ") + "\n")
            self.assertEqual(recipes_calling_make(dump(path)), expected, body)

    def test_detects_calls(self):
        for body in ("make all", "@make -C doc", "cd x && make", "gmake info", "$(MAKE) -C x"):
            with self.subTest(body=body):
                self.check(body, ["r"])

    def test_ignores_words_containing_make(self):
        for body in ("echo makefile", "cmake --build build", "./make_it.sh", "echo remake"):
            with self.subTest(body=body):
                self.check(body, [])


class MakefileTest(unittest.TestCase):
    """R3: the targets are gone from the root Makefile."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(RIOTBASE, "Makefile"), encoding="utf-8") as file:
            cls.text = file.read()

    def test_no_rule_for_migrated_targets(self):
        for target in MIGRATED:
            with self.subTest(target=target):
                self.assertIsNone(re.search(rf"^{re.escape(target)}\s*:", self.text, re.M))
                phony = " ".join(re.findall(r"^\.PHONY:(.*)$", self.text, re.M)).split()
                self.assertNotIn(target, phony)

    def test_make_treats_them_as_unknown(self):
        for target in MIGRATED:
            with self.subTest(target=target):
                result = run(["make", "--no-print-directory", "-n", target], cwd=RIOTBASE)
                self.assertIn(f'unrecognized target "{target}"', result.stdout)
                self.assertNotIn(MIGRATED[target].split()[0], result.stdout)

    def test_welcome_text_points_to_just(self):
        before, after = self.text.split("moved to just (run 'just --list')", 1)
        moved = after.splitlines()[1].split('"')[1].split()
        for target in MIGRATED:
            with self.subTest(target=target):
                self.assertIn(target, moved)
                self.assertNotIn(target, before)


class CallerTest(unittest.TestCase):
    """R4: no caller still runs the removed Make targets."""

    # These files name the old Make commands on purpose: the README documents
    # the migration ("before"), the tests assert their absence elsewhere.
    DOCUMENTS_THE_MIGRATION = (
        "dist/tools/task_layer",
        "dist/tools/features_yaml2mx/tests",
    )

    def test_no_reference_to_removed_make_targets(self):
        # --untracked: a local run sees the same files as CI after the commit.
        excludes = [f":(exclude){path}" for path in self.DOCUMENTS_THE_MIGRATION]
        result = run(["git", "grep", "--untracked", "-n", "-E",
                      r"make +(print-versions|generate-features)\b", "--", "."]
                     + excludes, cwd=RIOTBASE)
        if result.returncode == 128:
            self.skipTest("not a git checkout: " + result.stderr.strip())
        self.assertEqual(result.stdout, "", "still calls make for a moved target")

    def test_static_test_workflow_provides_just(self):
        path = os.path.join(RIOTBASE, ".github", "workflows", "static-test.yml")
        with open(path, encoding="utf-8") as file:
            text = file.read()
        self.assertIn("tool: just@", text)
        self.assertIn(':/usr/local/bin/just:ro', text)


class CiCheckScriptTest(unittest.TestCase):
    """R5: check_features_existing_inc_mk_is_up_to_date.sh with a stub just."""

    SCRIPT = os.path.join("dist", "tools", "ci", "check_features_existing_inc_mk_is_up_to_date.sh")
    MK = os.path.join("makefiles", "features_existing.inc.mk")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        os.makedirs(os.path.join(root, os.path.dirname(self.SCRIPT)))
        os.makedirs(os.path.join(root, "makefiles"))
        shutil.copy(os.path.join(RIOTBASE, self.SCRIPT), os.path.join(root, self.SCRIPT))
        with open(os.path.join(root, self.MK), "w", encoding="utf-8") as file:
            file.write("FEATURES_EXISTING := \\\n    #\n")
        self.bindir = os.path.join(root, "bin")
        os.makedirs(self.bindir)
        self.args_file = os.path.join(root, "just.args")

    def stub_just(self, action):
        write_executable(os.path.join(self.bindir, "just"), textwrap.dedent(f"""\
            #!/bin/sh
            echo "$@" > "{self.args_file}"
            {action}
            """))

    def run_check(self):
        env = dict(os.environ, PATH=self.bindir + os.pathsep + os.environ["PATH"])
        return run(["sh", os.path.join(self.tmp.name, self.SCRIPT)], env=env)

    def test_up_to_date_passes_and_calls_just_recipe(self):
        self.stub_just("exit 0")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with open(self.args_file, encoding="utf-8") as file:
            args = file.read().split()
        self.assertEqual(args[0], "--justfile")
        self.assertEqual(os.path.normpath(args[1]), os.path.join(self.tmp.name, "justfile"))
        self.assertEqual(args[2:], ["generate-features"])

    def test_stale_file_fails_with_just_hint(self):
        self.stub_just(f'echo "    feat_new \\\\" >> "{os.path.join(self.tmp.name, self.MK)}"')
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Forgot to run just generate-features", result.stdout)

    def test_failing_just_fails_the_check(self):
        self.stub_just("exit 3")
        self.assertEqual(self.run_check().returncode, 1)


@unittest.skipIf(JUST is None, "just is not installed")
class PrintVersionsParityTest(unittest.TestCase):
    """R1 for print-versions: just prints exactly what the script prints."""

    def test_same_stdout_as_script(self):
        script = run([MIGRATED["print-versions"]], cwd=RIOTBASE)
        recipe = run([JUST, "--justfile", JUSTFILE, "print-versions"], cwd=RIOTBASE)
        self.assertEqual(recipe.returncode, script.returncode)
        self.assertEqual(recipe.stdout, script.stdout)


@unittest.skipIf(JUST is None, "just is not installed")
class ReachabilityTest(unittest.TestCase):
    """R6 (decision 2026-11-20): the recipes may be called from any directory
    of the repository, because their result does not depend on the directory.
    Make offered them only at the root; just finds the root justfile from
    every subdirectory. Checked: same command, run in the repository root."""

    DIRECTORIES = ("examples/basic/hello-world", "tests/sys/shell", "boards", "sys")

    def test_same_command_from_every_directory(self):
        for target, command in MIGRATED.items():
            for directory in self.DIRECTORIES:
                with self.subTest(target=target, directory=directory):
                    result = run([JUST, "--dry-run", target], cwd=os.path.join(RIOTBASE, directory))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr.strip(), command)

    def test_recipes_run_in_the_repository_root(self):
        parsed = dump(JUSTFILE)
        for target in MIGRATED:
            with self.subTest(target=target):
                self.assertNotIn("no-cd", parsed["recipes"][target]["attributes"])


if __name__ == "__main__":
    unittest.main()
