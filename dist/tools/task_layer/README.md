Task layer (root `justfile`)
===========================

Repository commands that need no build system are run with
[just](https://just.systems) instead of GNU Make. Applications are still
built with `make` in their directory.

| Step (`dist/tools/migration/steps.yaml`) | Branch | Targets | Tests |
|---|---|---|---|
| `p3-task-layer-group1` | `migration/g1-01-print-versions-generate-features` | `print-versions`, `generate-features` | `tests/`, `../features_yaml2mx/tests/` |
| `p3-task-layer-group1-doc` | `migration/g1-02-doc` | `doc` | `../doccheck/tests/` |

Migrated targets
----------------

| Target              | Before                     | Now                        | Runs                                              |
|---------------------|----------------------------|----------------------------|---------------------------------------------------|
| `print-versions`    | `make print-versions`      | `just print-versions`      | `dist/tools/ci/print_toolchain_versions.sh`       |
| `generate-features` | `make generate-features`   | `just generate-features`   | `dist/tools/features_yaml2mx/features_yaml2mx.py` |

The first two were stateless group-1 targets: they read only repository files and do
not depend on `BOARD`, the application or build artifacts.

Rules
-----

- R1 A recipe runs the same command the Make target ran.
- R2 A recipe never calls `make`.
- R3 A migrated target is removed from the Makefile (`make <target>` fails).
- R4 Every caller (CI, docs, generated headers) uses `just`.
- R5 The CI check of the generated file keeps its behaviour.
- R6 A recipe may be reachable from every directory only if its result does not
  depend on the directory (checked per target, see
  `riot-build-config-thesis/docs/05-migration-concept/reachability/`).

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
| R6   | `ReachabilityTest`                                           | same `--dry-run` command from four subdirectories; recipes have no `[no-cd]` |
| R5   | `CiCheckScriptTest`                                          | script copy in a temporary tree with a stub `just`: up to date, stale, failing |

`features_yaml2mx/tests/test_features_yaml2mx.py` tests the generator itself:
nested groups, sorted and order-independent output, header text, idempotence,
unique feature names and that the committed `features_existing.inc.mk` is
up to date.

The tests of the first step were checked against deliberate defects: each of these changes
makes at least one test fail: a recipe calling `make`, the Make target added
again, the CI script ignoring a failing `just`, the generator hint pointing
to `make`, unsorted output, a README still naming `make generate-features`.

Step `p3-task-layer-group1-doc`: `doc`
--------------------------------------

`just doc` builds the HTML API documentation in `doc/doxygen/html` (with the
tag file `html/riot.tag`). It runs the steps `make doc` ran, in the same
order:

| Step (private recipe) | Before (Make) | Runs |
|---|---|---|
| `_doc-feature-list` | root `Makefile`, rule `doc` | `features_yaml2mx.py features.yaml --output-md doc/doxygen/src/feature_list.md` |
| `_doc-graphviz-check` | `doc/doxygen/Makefile`, `graphviz-check` | fails with the same message if `dot` is missing |
| `_doc-changelog` | `doc/doxygen/Makefile`, `src/changelog.md` | `generate-changelog.py` (always, like `doc-ci` with `-B`) |
| body of `doc` | `doc/doxygen/Makefile`, `html` | `riot.doxyfile` + `GENERATE_HTML`/`GENERATE_TAGFILE` piped to `$DOXYGEN` in `doc/doxygen` |
| `_doc-doxygen-version` | `doc/doxygen/Makefile`, `doxygen-version` | warning if Doxygen is older than `doxygen_min_version` |

`DOXYGEN` and `TAGFILE` are read from the environment or the command line
(`just DOXYGEN=/path/to/doxygen doc`), like `?=` in Make. Colours follow the
Make rule: only if stdout and stderr are terminals and `CC_NOCOLOR` is not 1.
The exit status of a failing step is 1 (Make reported every failing recipe
as 2). `STRIP_FROM_INC_PATH_LIST`, still exported by `doc/doxygen/Makefile`,
is not referenced by `riot.doxyfile` and is therefore not needed.

### `doc-man`, `doc-latex`, `doc-ci` stay in Make

Each step exists once, in the justfile. Make may call just (a just recipe
never calls make), so the Make targets that need the same steps delegate:

- root `doc-man`/`doc-latex`: `just _doc-feature-list`, then
  `doc/doxygen` (`graphviz-check`, `src/changelog.md` and `doxygen-version`
  run `just _doc-graphviz-check`, `_doc-changelog`, `_doc-doxygen-version`;
  the `man`/`latex` Doxygen runs stay in Make);
- `doc-ci` (root → `doc/doxygen`): downloads the required Doxygen as before,
  then runs `just DOXYGEN=<downloaded doxygen> doc` instead of a recursive
  `make doc`;
- `doxygen_min_version` is defined in the justfile; `doc/doxygen/Makefile`
  reads it with `sed` for the download of `doc-ci`, without needing just.

So `doc-man`, `doc-latex` and `doc-ci` now need just installed. The rules
`doc` (root, `doc/doxygen`, `Makefile.include`) and `html` are removed.
Because `doc` is also a directory, the root Makefile routes it explicitly to
the `.DEFAULT` message (otherwise Make would report it as up to date).

Callers: `dist/tools/doccheck/check.sh` runs `just doc` (or `make doc-ci` on
Linux x86_64, as before); `dist/tools/ci/static_tests.sh` lists `just` as a
dependency of that check (the static-test workflow already provides it);
guides and `doc/starlight` name `just doc`. `release-notes.txt` is history and
unchanged.

### Unit tests

```sh
python3 -m unittest discover -s dist/tools/doccheck/tests -v
```

Doxygen is not needed: real runs use stub `doxygen`, `dot`, `just`, `make`
and `uname` programs and temporary trees.

| Rule | Test class (`../doccheck/tests/test_doc_task.py`) | How |
|---|---|---|
| R1 | `DocRecipeContractTest`, `CheckRecipesTest`, `DocRunInTemporaryTreeTest` | dump (dependencies, order, working directory), dry run, `DOXYGEN`/`TAGFILE` override; exact messages and exit status of the checks; `just doc` in a temporary copy (Doxygen input, cwd, generated pages, failure paths) |
| R2 | `DocRecipeContractTest` | make detector of `tests/test_justfile.py`; the scripts it runs start no process |
| R3 | `MakeNoLongerKnowsDocTest` | `make -n doc` at the root, in `doc/doxygen` and in an application; no rule, `.PHONY` entry or `GENERATE_HTML` in Make |
| R4 | `CallerTest`, `DetectorTest`, `MakeDelegatesToJustTest` | `git grep` + detector with positive and negative samples; `doc-man`/`doc-latex` with stub just record the delegated steps; `doc-ci` ends with `just DOXYGEN=… doc`; one minimum version |
| R5 | `DoccheckScriptTest` | `check.sh` copy with stubs: clean output, warning, excluded warning, `make doc-ci` on x86_64, output (not exit status) decides |

Parity: no Doxygen is installed here, so the HTML output was not compared.
With a stub `doxygen`, `make doc` on the base commit and `just doc` produced
identical `feature_list.md`, `changelog.md`, Doxygen input, working directory
and messages (only Make's own command echo differs); `make doc-man` likewise.

Deliberate defects, each detected by at least one test: Doxygen run without
the tag file, a changed GraphViz message, the version warning before
Doxygen, a recipe calling `make`, `doc` back in `Makefile.include`, the root
rule for `doc` removed, a guide naming `make doc`, `doc-ci` calling
`make doc` again, the GraphViz check duplicated in Make, the minimum version
defined twice, `check.sh` calling `make doc`, its exclude list ignored.
