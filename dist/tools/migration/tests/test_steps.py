#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for the register of migration steps (steps.yaml) and its runner.

They enforce the organisation of the migration tests:

* O1  the register is consistent (keys, groups, unique targets, existing
      test directories with test modules, hardware targets have a board test);
* O2  every target that is run with just is registered, and every registered
      just target exists, so no migrated target can exist without tests;
* O3  only the migration-tests workflow runs migration tests, and it takes
      its jobs from the register instead of listing test directories.

Run: python3 -m unittest discover -s dist/tools/migration/tests -v
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
RIOTBASE = os.path.normpath(os.path.join(TOOL_DIR, "..", "..", ".."))
WORKFLOWS = os.path.join(RIOTBASE, ".github", "workflows")
MIGRATION_WORKFLOW = "migration-tests.yml"
sys.path.insert(0, TOOL_DIR)

import run_tests as rt  # noqa: E402  pylint: disable=wrong-import-position

JUST = shutil.which("just")

VALID_STEP = {
    "id": "p9-example-step",
    "title": "Example",
    "group": "2A",
    "targets": [{"name": "info-x", "now": "just info-x", "hardware": False}],
    "tests": ["tests"],
    "requires": {"pip": [], "tools": []},
    "docs": "README.md",
}


class RegisterIsConsistentTest(unittest.TestCase):
    """O1 for the real steps.yaml."""

    def test_no_problems(self):
        self.assertEqual(rt.validate(rt.load()), [])


class ValidatorTest(unittest.TestCase):
    """O1: the validator finds each kind of problem (negative samples)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, "tests"))
        with open(os.path.join(self.tmp.name, "tests", "test_x.py"), "w", encoding="utf-8"):
            pass
        with open(os.path.join(self.tmp.name, "README.md"), "w", encoding="utf-8"):
            pass

    def problems(self, *steps):
        return rt.validate(list(steps), root=self.tmp.name)

    def changed(self, **changes):
        step = copy.deepcopy(VALID_STEP)
        step.update(changes)
        return step

    def assert_problem(self, text, *steps):
        found = self.problems(*steps)
        self.assertTrue(any(text in p for p in found), f"{text!r} not in {found}")

    def test_valid_step_has_no_problem(self):
        self.assertEqual(self.problems(VALID_STEP), [])

    def test_unknown_group(self):
        self.assert_problem("group must be", self.changed(group="4"))

    def test_bad_id(self):
        self.assert_problem("id must look like", self.changed(id="Task Layer"))

    def test_duplicate_id(self):
        other = self.changed(targets=[{"name": "info-y", "now": "just info-y",
                                       "hardware": False}])
        self.assert_problem("duplicate id", VALID_STEP, other)

    def test_target_in_two_steps(self):
        self.assert_problem("already in step", VALID_STEP, self.changed(id="p9-other"))

    def test_missing_tests(self):
        self.assert_problem("no tests", self.changed(tests=[]))

    def test_test_directory_does_not_exist(self):
        self.assert_problem("does not exist", self.changed(tests=["missing"]))

    def test_test_directory_without_test_module(self):
        os.makedirs(os.path.join(self.tmp.name, "empty"))
        self.assert_problem("has no test_", self.changed(tests=["empty"]))

    def test_hardware_target_needs_board_test(self):
        flash = {"name": "flash", "now": "just flash", "hardware": True}
        self.assert_problem("needs 'board_test'", self.changed(targets=[flash]))

    def test_unknown_key(self):
        self.assert_problem("unknown key 'test'", self.changed(test=["tests"]))

    def test_missing_key(self):
        step = copy.deepcopy(VALID_STEP)
        del step["requires"]
        self.assert_problem("missing key 'requires'", step)

    def test_group_id_accepted_and_bad_ones_rejected(self):
        self.assertEqual(self.problems(self.changed(id="g2a-01-info-x")), [])
        for bad in ("g0-1-config", "g9-01-x", "G0-01-x", "g0-01"):
            with self.subTest(id=bad):
                self.assert_problem("id must look like", self.changed(id=bad))


class FoundationStepTest(unittest.TestCase):
    """O1 for group G0: no migrated target, but what it provides."""

    setUp = ValidatorTest.setUp
    problems = ValidatorTest.problems
    changed = ValidatorTest.changed
    assert_problem = ValidatorTest.assert_problem

    FOUNDATION_STEP = {**VALID_STEP, "id": "g0-01-example", "group": "G0", "targets": [],
                       "provides": [{"name": "gen-x", "now": "just gen-x",
                                     "hardware": False}]}

    def foundation(self, **changes):
        step = copy.deepcopy(self.FOUNDATION_STEP)
        step.update(changes)
        return step

    def test_valid_foundation_step(self):
        self.assertEqual(self.problems(self.foundation()), [])

    def test_foundation_step_migrates_no_target(self):
        self.assert_problem("migrates no target", self.foundation(targets=VALID_STEP["targets"]))

    def test_foundation_step_needs_provides(self):
        step = self.foundation()
        del step["provides"]
        self.assert_problem("needs 'provides'", step)

    def test_provides_only_in_foundation_step(self):
        self.assert_problem("'provides' only", self.changed(provides=[]))

    def test_empty_targets_outside_foundation(self):
        self.assert_problem("no targets", self.changed(targets=[]))

    def test_provided_entries_are_checked_like_targets(self):
        entry = {"name": "gen-x", "now": "just gen-x", "hardware": False, "x": 1}
        self.assert_problem("unknown key 'x'", self.foundation(provides=[entry]))
        self.assert_problem("already in step",
                            self.foundation(provides=[{**VALID_STEP["targets"][0]}]),
                            VALID_STEP)

    def test_selection_by_provided_name(self):
        steps = [VALID_STEP, self.foundation()]
        self.assertEqual([s["id"] for s in rt.select(steps, target="gen-x")],
                         ["g0-01-example"])
        self.assertEqual([s["id"] for s in rt.select(steps, group="G0")], ["g0-01-example"])


class SelectionTest(unittest.TestCase):
    def setUp(self):
        other = copy.deepcopy(VALID_STEP)
        other.update(id="p6-build", group="3",
                     targets=[{"name": "all", "now": "cmake --build", "hardware": False}])
        self.steps = [VALID_STEP, other]

    def test_select_by_group_step_and_target(self):
        self.assertEqual([s["id"] for s in rt.select(self.steps, group="3")], ["p6-build"])
        self.assertEqual([s["id"] for s in rt.select(self.steps, step="p9-example-step")],
                         ["p9-example-step"])
        self.assertEqual([s["id"] for s in rt.select(self.steps, target="all")], ["p6-build"])

    def test_matrix_has_one_job_per_step(self):
        jobs = rt.matrix(self.steps)["include"]
        self.assertEqual([j["id"] for j in jobs], ["p9-example-step", "p6-build"])
        self.assertEqual(set(jobs[0]), {"id", "group", "pip", "tools"})

    def test_matrix_command_prints_json(self):
        result = subprocess.run([sys.executable, os.path.join(TOOL_DIR, "run_tests.py"),
                                 "--matrix"], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        jobs = json.loads(result.stdout)["include"]
        self.assertEqual([j["id"] for j in jobs], [s["id"] for s in rt.load()])


@unittest.skipIf(JUST is None, "just is not installed")
class EveryJustTargetIsRegisteredTest(unittest.TestCase):
    """O2: register and justfile describe the same set of just targets."""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run([JUST, "--justfile", os.path.join(RIOTBASE, "justfile"),
                                 "--dump", "--dump-format", "json"],
                                capture_output=True, text=True, check=True)
        recipes = json.loads(result.stdout)["recipes"]
        cls.recipes = {n for n, r in recipes.items() if not r["private"]}
        cls.registered = {t["now"].split()[1] for s in rt.load() for t in rt.entries(s)
                          if t["now"].startswith("just ")}

    def test_every_recipe_is_registered_with_tests(self):
        self.assertEqual(sorted(self.recipes - self.registered), [],
                         "recipe without an entry (and tests) in steps.yaml")

    def test_every_registered_just_target_exists(self):
        self.assertEqual(sorted(self.registered - self.recipes), [])


class WorkflowOrganisationTest(unittest.TestCase):
    """O3: migration tests run in one workflow, driven by the register."""

    def test_only_migration_workflow_runs_registered_tests(self):
        test_dirs = [d for s in rt.load() for d in s["tests"]] + ["dist/tools/migration/tests"]
        for name in sorted(os.listdir(WORKFLOWS)):
            if name == MIGRATION_WORKFLOW:
                continue
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as file:
                text = file.read()
            for test_dir in test_dirs:
                with self.subTest(workflow=name, test_dir=test_dir):
                    self.assertNotIn(test_dir, text)

    def test_migration_workflow_takes_jobs_from_register(self):
        with open(os.path.join(WORKFLOWS, MIGRATION_WORKFLOW), encoding="utf-8") as file:
            text = file.read()
        self.assertIn("run_tests.py --matrix", text)
        self.assertIn("fromJSON(needs.register.outputs.matrix)", text)
        self.assertIn("run_tests.py --step", text)
        for step in rt.load():
            for test_dir in step["tests"]:
                with self.subTest(test_dir=test_dir):
                    self.assertNotIn(test_dir, text, "list the step in steps.yaml instead")


if __name__ == "__main__":
    unittest.main()
