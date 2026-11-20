Task layer (root `justfile`)
===========================

Repository commands that need no build system are run with
[just](https://just.systems) instead of GNU Make. This proof of concept moves
two of them; applications are still built with `make` in their directory.

Migrated targets
----------------

| Target              | Before                     | Now                        | Runs                                              |
|---------------------|----------------------------|----------------------------|---------------------------------------------------|
| `print-versions`    | `make print-versions`      | `just print-versions`      | `dist/tools/ci/print_toolchain_versions.sh`       |
| `generate-features` | `make generate-features`   | `just generate-features`   | `dist/tools/features_yaml2mx/features_yaml2mx.py` |

Both were stateless group-1 targets: they read only repository files and do
not depend on `BOARD`, the application or build artifacts.

Rules
-----

- R1 A recipe runs the same command the Make target ran.
- R2 A recipe never calls `make`.
- R3 A migrated target is removed from the Makefile (`make <target>` fails).
- R4 Every caller (CI, docs, generated headers) uses `just`.
- R5 The CI check of the generated file keeps its behaviour.

Unit tests
----------

```sh
python3 -m unittest discover -s dist/tools/task_layer/tests -v
python3 -m unittest discover -s dist/tools/features_yaml2mx/tests -v
```

Requirements: Python 3, PyYAML, just 1.59.0 (tests that need just are skipped
without it). The tests build nothing and change no repository file. CI runs
them in the `migration-tests` workflow (step `p3-task-layer-group1` in
`dist/tools/migration/steps.yaml`).

| Rule | Test class (`tests/test_justfile.py`)                        | How                                                     |
|------|--------------------------------------------------------------|---------------------------------------------------------|
| R1   | `JustfileContractTest`, `PrintVersionsParityTest`            | `just --dump`, `just --dry-run`, stdout vs. the script  |
| R2   | `JustfileContractTest`, `MakeCallDetectorTest`               | parsed recipe bodies; detector checked on positive and negative samples |
| R3   | `MakefileTest`                                               | no rule/`.PHONY` entry; `make -n <target>` reports an unknown target |
| R4   | `CallerTest`                                                 | `git grep` for `make <target>`; workflow installs just |
| R5   | `CiCheckScriptTest`                                          | script copy in a temporary tree with a stub `just`: up to date, stale, failing |

`features_yaml2mx/tests/test_features_yaml2mx.py` tests the generator itself:
nested groups, sorted and order-independent output, header text, idempotence,
unique feature names and that the committed `features_existing.inc.mk` is
up to date.

The tests were checked against deliberate defects: each of these changes
makes at least one test fail: a recipe calling `make`, the Make target added
again, the CI script ignoring a failing `just`, the generator hint pointing
to `make`, unsorted output, a README still naming `make generate-features`.
