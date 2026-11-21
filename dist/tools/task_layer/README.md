Task layer (root `justfile`)
===========================

Repository commands that need no build system are run with
[just](https://just.systems) instead of GNU Make. Applications are still
built with `make` in their directory.

| Step (`dist/tools/migration/steps.yaml`) | Branch | Targets | Tests |
|---|---|---|---|
| `p3-task-layer-group1` | `migration/g1-01-print-versions-generate-features` | `print-versions`, `generate-features` | `tests/`, `../features_yaml2mx/tests/` |
| `p3-task-layer-group1-doc` | `migration/g1-02-doc` | `doc` | `../doccheck/tests/` |
| `p3-task-layer-group1-list-ttys` | `migration/g1-03-list-ttys` | `list-ttys` | `../usb-serial/tests/` |
| `g2c-03-pkg-clean` | `migration/g2c-03-pkg-clean` | `pkg-clean` | `../pkg_clean/tests/` |

just searches the root `justfile` upwards from the current directory, so
every recipe can also be called from an application directory (rule R6).

Migrated targets
----------------

| Target              | Before                                   | Now                      | Runs                                              | Step (`steps.yaml`) / branch |
|---------------------|------------------------------------------|--------------------------|---------------------------------------------------|------------------------------|
| `print-versions`    | `make print-versions` (root)             | `just print-versions`    | `dist/tools/ci/print_toolchain_versions.sh`       | `p3-task-layer-group1` / `migration/g1-01-print-versions-generate-features` |
| `generate-features` | `make generate-features` (root)          | `just generate-features` | `dist/tools/features_yaml2mx/features_yaml2mx.py` | `p3-task-layer-group1` / `migration/g1-01-print-versions-generate-features` |
| `doc`               | `make doc` (root, applications)          | `just doc`               | `doc/doxygen` (Doxygen, see below)                | `p3-task-layer-group1-doc` / `migration/g1-02-doc` |
| `list-ttys`         | `make list-ttys` (application directory) | `just list-ttys`         | `dist/tools/usb-serial/ttys.py`                   | `p3-task-layer-group1-list-ttys` / `migration/g1-03-list-ttys` |

All are stateless group-1 targets: they do not depend on `BOARD`, the
application or build artifacts.

### `list-ttys`

`make list-ttys` was defined in `Makefile.include`, so it was run from an
application directory. It ran `$(RIOTTOOLS)/usb-serial/ttys.py` without
arguments and without any Make variable. The recipe keeps this exactly:

- same command: the absolute path `<repository>/dist/tools/usb-serial/ttys.py`
  (`justfile_directory()`), no arguments;
- same working directory: `[no-cd]`, so it runs where it is called, as Make
  ran it in the application directory;
- no extra arguments: Make offered no way to pass arguments to `ttys.py`,
  so the recipe has no parameters and `just list-ttys --serial x` fails.
  For filters, call `dist/tools/usb-serial/ttys.py --help` directly.

It is not a hardware target: it only lists the serial devices the host
already knows (udev, via `pyudev`); it does not talk to a board, flash or
reset anything, and it works (with an empty table) when nothing is connected.

Not migrated: the PORT selection in `makefiles/tools/serial.inc.mk`
(`MOST_RECENT_PORT`, `TTY_SELECT_CMD`) also runs `ttys.py`, but as part of
the board configuration of a build. It stays in Make unchanged.

Effects: `make help` in an application lists the targets of the Make
database, so `list-ttys` no longer appears there; `just --list` shows it.
The welcome text of the root Makefile lists only root targets and is
unchanged. The zsh completion no longer offers `list-ttys` as a Make target.
`release-notes.txt` keeps `make list-ttys` as history.

Rules
-----

- R1 A recipe runs the same command the Make target ran.
- R2 A recipe never calls `make`.
- R3 A migrated target is removed from the Makefile (`make <target>` fails).
- R4 Every caller (CI, docs, generated headers) uses `just`.
- R5 Checks keep their behaviour (CI check of the generated file;
  for `list-ttys`: the PORT selection in `serial.inc.mk`).
- R6 A recipe may be reachable from every directory only if its result does not
  depend on the directory (checked per target, see
  `riot-build-config-thesis/docs/05-migration-concept/reachability/`).

Unit tests
----------

```sh
python3 -m unittest discover -s dist/tools/task_layer/tests -v
python3 -m unittest discover -s dist/tools/features_yaml2mx/tests -v
python3 -m unittest discover -s dist/tools/usb-serial/tests -v   # list-ttys
```

Requirements: Python 3, PyYAML, just 1.59.0 (tests that need just are skipped
without it); for `list-ttys` also GNU Make and `pyudev`. The tests build
nothing and change no repository file. CI runs them in the
`migration-tests` workflow, one job per step of
`dist/tools/migration/steps.yaml` (`p3-task-layer-group1`,
`p3-task-layer-group1-list-ttys`).

### `print-versions`, `generate-features` (step `p3-task-layer-group1`)

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

### `list-ttys` (step `p3-task-layer-group1-list-ttys`)

| Rule | Test class (`dist/tools/usb-serial/tests/test_list_ttys.py`) | How |
|------|---------------------------------------------------|-----|
| R1   | `JustfileContractTest`                            | `just --dump`: public, no parameters, `[no-cd]`; `just --dry-run list-ttys` prints the command Make ran (golden), from the root, from an application directory (upward search) and with `--justfile`/`--working-directory` |
| R1   | `CallingDirectoryAndArgumentsTest`                | copied justfile with a stub `ttys.py`: runs in the calling directory, with no arguments, exit code passed on; extra arguments are rejected |
| R1   | `OutputParityTest`                                | stdout, stderr and exit code of `just list-ttys` equal those of `ttys.py`, both run in `examples/basic/hello-world` (no device needed) |
| R2   | `JustfileContractTest`                            | make-call detector of `tests/test_justfile.py`, with a positive and a negative sample of this recipe's shape |
| R3   | `MakefileTest`, `UnknownTargetDetectorTest`       | no rule/`.PHONY` entry in any Makefile; `make -n list-ttys` in an application: `No rule to make target`; in the root: `unrecognized target`; not in `make help`; detector checked on positive and negative samples |
| R4   | `CallerTest`                                      | `git grep` for `make list-ttys` (excluding `release-notes.txt`, this directory and the tests); docs use `just list-ttys`; zsh completion; detector samples |
| R5   | `SerialPortSelectionTest`                         | `TTY_SELECT_CMD` for `nrf52840dk` with `MOST_RECENT_PORT=1` equals the value recorded before the migration; without it no command and `PORT=/dev/ttyACM0` |
| –    | `RegisterTest`                                    | the step is in `steps.yaml` with this test directory |

Mutation probe (2026-11-20; each file copied before the change and restored
from the copy):

| Rule | Defect | Failing tests |
|------|--------|---------------|
| R1   | recipe passes `--most-recent` | 4 |
| R1   | `[no-cd]` removed (runs in the repository root) | 2 |
| R1   | recipe accepts and passes extra arguments | 2 |
| R2   | recipe calls `make -C … list-ttys` | 6 |
| R3   | rule `list-ttys:` added to `Makefile.include` again | 3 |
| R4   | `rpl.mdx` back to `make list-ttys` | 2 |
| R4   | zsh completion offers `list-ttys` again | 1 |
| R5   | `serial.inc.mk` drops the `serial` output format | 1 |
| –    | step removed from `steps.yaml` | 1 (+1 register test O2) |

### `pkg-clean` (step `g2c-03-pkg-clean`, group 2C)

`make pkg-clean` (root `Makefile`) printed `Cleaning all package sources`
and ran `rm -rf build/pkg` in the repository root. `just pkg-clean` does the
same, with the same two lines on stdout and nothing on stderr:

- the directory is fixed: `<repository>/build/pkg`. The root Makefile never
  read `BUILD_DIR` or `PKGDIRBASE` (they belong to `Makefile.include`), so
  `make pkg-clean PKGDIRBASE=…` removed `build/pkg` as well; the recipe
  ignores both too. An application built with another `PKGDIRBASE` cleans
  its packages with `make clean-pkg`/`distclean` in its directory, as before;
- `pkg-clean` has no parameters; it runs the private steps
  `_pkg-clean <dir> <mode>` with `justfile_directory()` and mode `echo`;
- the steps are a `/bin/sh` script without make or Make file: check that
  `<dir>` is absolute and the mode is `echo`, `silent` or `dry-run`, `cd`
  to `<dir>` (`set -e`), then `rm -rf build/pkg`. The path is a shell
  variable, so just cannot override it;
- exit status: 0, also when `build/pkg` does not exist; if `rm` fails, the
  same `rm:` message and status 1 (Make reported 2).

Root `distclean` (stays in Make): its prerequisite `pkg-clean` is replaced by
`_pkg-clean`, at the same place, which runs the steps from the justfile next
to the Makefile: `just --justfile <Makefile directory>/justfile _pkg-clean
"$(CURDIR)" <mode>`. Make may call just, a just recipe never calls make, and
the cleaning exists only in the justfile. `make distclean` now needs just.
Its behaviour is unchanged (compared live with the base commit
`74a0fb9743`, GNU Make 4.3):

| Call | Before and now |
|---|---|
| `make distclean`, with or without `--no-print-directory`, `-k` | same lines, same order, same effect |
| `make -s distclean` | silent: mode `silent` prints only `Cleaning all package sources`, as Make hid the command line |
| `make -n distclean` (also `-ns`) | prints `echo "Cleaning all package sources"` and `rm -rf build/pkg` and changes nothing: Make expands the recipe with `$(shell just … dry-run)`, which only prints the commands |
| `make -q distclean` | same output and status 1 |
| `make -f <repository>/Makefile distclean` in another directory | as before, the build/pkg of CURDIR is cleaned (Make passes CURDIR; the justfile is found next to the Makefile). Without `makefiles/` and `doc/` there, Make already failed in `docclean` (with `-k` it went on and removed `<CURDIR>/build/pkg`, and still does); from a second RIOT tree, that tree is cleaned |

The mode comes from the single-letter options in `MAKEFLAGS` (`n` →
`dry-run`, `s` → `silent`, otherwise `echo`). The new Make parts are at the
end of the Makefile and the removed lines are balanced, so Make's messages
keep their line numbers. Only remaining difference: `make -t distclean`
(touch mode) used to create an empty file `pkg-clean` in the root, because
the old target was not `.PHONY`; `_pkg-clean` is phony and creates nothing.
A non-phony Make target named `pkg-clean` would contradict R3.

Reachability (R6): reachable from every directory. C1: same output, exit
status and effect from the root, an application, `doc/doxygen`,
`makefiles` and `build/other` (a `build/pkg` below the calling directory is
not touched). C2: the package sources are shared by all applications and
boards (`nrf52840dk` included), the command takes no application or board.
C3: it only removes `<repository>/build/pkg`, idempotently. Note: in an
application `just pkg-clean` removes the packages of all applications; the
application-level `make clean-pkg` (only its packages) is a different
target and is unchanged.

Safety: `just pkg-clean` deletes nothing outside `<repository>/build/pkg`.
Arguments (`just pkg-clean /`) and variable overrides
(`just BUILD_DIR=… pkg-clean`, `--set`) are refused by just;
`BUILD_DIR`/`PKGDIRBASE` in the environment and `--working-directory` are
ignored; a symlink `build/pkg` loses only the link, not its target. The
private steps, which Make calls, remove exactly `<dir>/build/pkg` (as
`make -f` did for CURDIR); they refuse a relative or empty `<dir>` and an
unknown mode, and stop (`set -e`) if `<dir>` cannot be entered. As with
Make, a symlinked `build` directory is followed.

```sh
python3 -m unittest discover -s dist/tools/pkg_clean/tests -v
```

| Rule | Test class (`../pkg_clean/tests/test_pkg_clean.py`) | How |
|---|---|---|
| R1 | `RecipeContractTest`, `EffectTest`, `MakeParityTest` | `just --dump`: public, no parameters, steps with the repository directory and mode `echo`, one fixed `rm`; real run in a temporary tree: stdout, stderr, exit status, exactly `build/pkg` removed, idempotent, failure output; live comparison with `make pkg-clean` of the base commit (also with `BUILD_DIR`/`PKGDIRBASE` set) |
| R2 | `RecipeContractTest`, `NoMakeTest` | make detector (with samples) on both recipes, no Make file or `$(`; real run with a recording `make`/`gmake` first on `PATH` |
| R3 | `MakefileTest` | no rule/`.PHONY` entry; `make pkg-clean` (temporary tree): `unrecognized target`, exit 2, nothing removed; welcome text lists it under just |
| R4 | `CallerTest`, `MakefileTest` | `git grep` for `make … pkg-clean` (with detector samples); `_pkg-clean` only runs the just steps, no `rm` in the Makefile |
| R5 | `DistcleanTest` | `make distclean` in a temporary tree (stub Makefiles for `doc/` and an application), live against the base commit: default, `-s`, `-n`, `-ns`, `-k`, `-sk`, `-q`, `-n -k`, `--silent`, `--just-print`, with and without `--no-print-directory`; `-f` from a non-RIOT directory and from a second tree (with `-k`, `-s -k`, `-n -k`); recorded output; `-t` difference; fails without just |
| R6 | `ReachabilityTest` | real run from five directories of a temporary tree; same `--dry-run` from five repository directories |
| S | `SafetyTest` | refused arguments and overrides, ignored environment and `--working-directory`, symlinked `build/pkg`, failing `cd`; steps: relative directory and unknown mode refused, only `<dir>/build/pkg` removed, `dry-run` changes nothing |
| – | `RegisterTest` | step in `steps.yaml` (group 2C, hardware: false) |

Mutation probe (2026-11-22; each file copied before the change and restored
from the copy; every defect detected; counts include subtests):

| Rule | Defect | Failing tests |
|---|---|---|
| R1 | message changed | 36 |
| R1 | `pkg=build` (removes all of `build/`) | 36 |
| R1 | `rm -rf build/pkg/*` (hidden entries stay) | 29 |
| R2 | steps call `make` | 3 |
| R3 | rule `pkg-clean` back in the root Makefile | 7 |
| R3 | welcome text lists `pkg-clean` under Make | 1 |
| R4 | `_pkg-clean` cleans itself (logic duplicated) | 8 |
| R5 | `_pkg-clean` after the applications | 19 |
| R5 | `_pkg-clean` dropped from `distclean` | 24 |
| R5 `-s` | `-s` not passed on (always `echo`) | 7 |
| R5 `-s` | mode `silent` also hides the message | 8 |
| R5 `-n` | `-n` not detected (just call shown) | 7 |
| R5 `-n` | mode `dry-run` removes `build/pkg` | 8 |
| R5 `-f` | repository root instead of CURDIR | 7 |
| R5 `-f` | justfile taken from CURDIR again | 9 |
| R5 `-f` | extra line before the includes (line numbers) | 4 |
| R6 | `pkg-clean` acts in the calling directory | 8 |
| S | no `cd` (acts in the working directory) | 11 |
| S | no `set -e` (failed `cd` falls through) | 2 |
| S | `rm -rf build/pkg/` (follows a symlink) | 2 |
| S | directory from `PKGDIRBASE` | 2 |
| S | relative directory accepted | 6 |
| S | unknown mode accepted | 4 |
| – | step removed from `steps.yaml` | 1 error (+2 failures, 2 errors in `../migration/tests`) |
