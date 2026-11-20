Migration tests
===============

Every step of the migration away from GNU Make comes with unit tests. This
directory keeps them organised:

| File | Purpose |
|---|---|
| `steps.yaml` | Register: step → group → migrated targets → test directories → CI requirements |
| `run_tests.py` | Runs the tests of all steps, or of one step, group or target |
| `tests/test_steps.py` | Checks the register and the CI organisation |
| `../../../.github/workflows/migration-tests.yml` | CI: one job per step, generated from `steps.yaml` |

Usage
-----

```sh
dist/tools/migration/run_tests.py --list                 # steps and their targets
dist/tools/migration/run_tests.py                        # all steps
dist/tools/migration/run_tests.py --step p3-task-layer-group1
dist/tools/migration/run_tests.py --group 1
dist/tools/migration/run_tests.py --target print-versions
```

In CI, the job `register` checks the register and builds the matrix. Then
one job per step runs, named `<step id> (group <n>)`, so a failure shows
which step and which targets are affected.

Adding a migration step
-----------------------

1. Migrate the target(s) and write unit tests next to the code they test
   (`<tool>/tests/test_*.py`), following the pattern of the group.
2. Document the step in a README (targets, rules, rule → test matrix).
3. Add the step to `steps.yaml`: `id` (`<roadmap phase>-<topic>`), `group`,
   `targets` (`name`, `now`, `hardware`; `board_test` for hardware targets),
   `tests`, `requires`, `docs`.
4. Run `dist/tools/migration/run_tests.py --step <id>` and
   `python3 -m unittest discover -s dist/tools/migration/tests`.

Do not add test directories to any workflow. The register tests fail if a
workflow other than `migration-tests.yml` runs migration tests, or if that
workflow lists test directories itself.

Rules enforced by `tests/test_steps.py`
---------------------------------------

| Rule | Fails when |
|---|---|
| O1 consistent register | unknown or missing key, unknown group, duplicate step id or target, missing test directory or test module, hardware target without `board_test` |
| O2 no migrated target without tests | a public `just` recipe is not registered, or a registered `just` target does not exist |
| O3 one place for CI | another workflow runs a registered test directory, or `migration-tests.yml` lists test directories instead of using the register |

Hardware targets
----------------

CI runs only unit tests; the command line of `flash`, `term` or `debug` is
checked with stub tools. Whether the board really works afterwards is a
board test, described per target in `board_test` and run manually on the
nRF52840 board.
