Binary distribution without Make: distribution data (migration step G3-3)
==========================================================================

`just bindist <application> <board>` does what GNU Make's target `bindist`
does: it builds the application (`all`, without Make: the CMake/Ninja build
of step G3-1) and creates the directory `bindist/` in the application
directory with the files Make puts there. Inputs are **data only**: the YAML
data of the repository, the resolver (G0-2), the build data (G3-1) and the
distribution data of this step. No make process is started, no Make file is
opened, no Make syntax is parsed.

```sh
just bindist examples/advanced/bindist nrf52840dk
just bindist examples/advanced/bindist nrf52840dk DIST_FILES='Makefile README.md'   # VAR=VALUE as for make
dist/tools/bindist/bindist.py bindist -C <app> BOARD=<board> [-B <dir>] [-j N] [-n] [--no-build] [VAR=VALUE…]
```

`-n` prints the commands (as `make -n`), `--no-build` uses the existing
build products (as `make -o all bindist` in an application without
`bindist/`). Exit status: 0; 1 a failed command; 2 an error of the
configuration (Make's `$(error)`); 3 the request is outside the data.

Scope: `examples/advanced/bindist` on **nrf52840dk** (decision D22; not
native64). It is the application of the scope that names `DIST_FILES` and
`BIN_USEMODULE`; for hello-world and gnrc_networking `bindist` copies only
the binary.

What Make's `bindist` does (base 8324f6c5e9)
--------------------------------------------

`makefiles/bindist.inc.mk` (included by `build.mk`, the `version` section of
`build.yaml`):

| Input | Where | Value for the sample |
|---|---|---|
| `DIST_FILES` | the application (`riot-app.yaml` → `Makefile`: `DIST_FILES += Makefile`) and `bindist.inc.mk:4` (`$(BIN_USEMODULE:%=bin/$(BOARD)/%/*.o)`) | `Makefile bin/nrf52840dk/abc/*.o bin/nrf52840dk/application_bindist/*.o` |
| `BIN_USEMODULE`, `BIN_DIRS` | the application; `bindist.inc.mk:2` adds the modules to USEMODULE (resolver, G0-2), `bindist.build.yaml` the directories to DIRS (G3-1) | `abc application_bindist`, `abc` |
| `bin/$(BOARD)/$(APPLICATION).bin` | the recipe, literally `bin/$(BOARD)` (Make's default BINDIR) | `bin/nrf52840dk/bindist.bin` |
| `RIOT_VERSION` | build data (`makefiles/git_version.build.yaml`) | `git describe` of RIOTBASE |
| `git -C $(RIOTBASE) describe` | run by the shell in the recipe | |

The recipe (`bindist: all`, run in the application directory, each line by
`/bin/sh -c`):

```make
@mkdir -p bindist
@for i in $(DIST_FILES) ; do echo Copying $$i to bindist. ; cp -a --parents $$i bindist ; done
@cp -a bin/$(BOARD)/$(APPLICATION).bin bindist
@echo "BINDIST_RIOT_VERSION=$(RIOT_VERSION)" > bindist/Makefile.distcheck
@echo "BINDIST_GIT_HEAD=$$(git -C $(RIOTBASE) describe)" >> bindist/Makefile.distcheck
```

Output: `bindist/Makefile`, `bindist/bin/nrf52840dk/abc/abc.o`,
`bindist/bin/nrf52840dk/application_bindist/main.o` (with the directories
`bin`, `bin/nrf52840dk`, `abc`, `application_bindist`: `cp -a --parents`
keeps mode and timestamps of files and directories), `bindist/bindist.bin`
and `bindist/Makefile.distcheck` (new). The shell expands the `*.o`
patterns; a pattern without a match is copied literally and `cp` fails; the
loop's status is the last `cp`'s, so only a failing last item stops Make.
`check_bindist`/`prepare_check_bindist` (building from a distribution, run
inside `bindist/`) are other targets and stay Make.

Data model
----------

The one setting of `bindist.inc.mk` that was not data yet - the objects of
the binary modules in DIST_FILES - is a rule list next to it, the **single
source**; `bindist.inc.mk` includes the adapter generated from it
(`just generate-dist-data`, private recipe; `bindist.py generate --check` in
the tests) as its first statement:

| Make file | distribution data | adapter (generated) | content |
|---|---|---|---|
| `makefiles/bindist.inc.mk` | `bindist.dist.yaml` | `bindist.dist.inc.mk` | `DIST_FILES += $(patsubst %,bin/$(BOARD)/%/*.o,$(BIN_USEMODULE))` |

Format: `{schema: 3, rules}` with the rule language of
`dist/tools/config_data/README.md` (schema 3) without the build-only
constructs `section` and `stand_in` (validator and generator in
`distdata.py`; config_data is not changed). The data uses a selection with
`pattern` (`$(patsubst)`), the same words as Make's substitution reference.
The value stays recursive (`+=`), so BOARD and BIN_USEMODULE are read when
the recipe is expanded, as before; a `DIST_FILES=…` on the command line
replaces it, as in Make. Already data before this step: the application's
DIST_FILES/BIN_USEMODULE/BIN_DIRS (`riot-app.yaml`, G0-1), the directories
of the binary modules (`bindist.build.yaml`, G3-1/G0-3), RIOT_VERSION (build
data); the module list `USEMODULE += …BIN_USEMODULE` is the resolver's
(`pipeline.application`, G0-2). The build without Make does not read the
distribution data (DIST_FILES is no build variable).

Algorithm, not data (`bindist.py`, each part names the Make lines it
replaces): the read order (the distribution data where Make includes its
adapter, before `bindist.build.yaml`), the recipe text (`bindist.inc.mk:14-23`
with the variables expanded, `$$` as `$`, backslash-newline kept and the
recipe tab after it removed, `@` stripped), running it (each line with
`/bin/sh -c` in the application directory, stop at the first failing line,
the environment of Make's exports and command line variables), and the
build in Make's BINDIR.

Build directory: Make's recipe takes the objects and the binary from
`bin/$(BOARD)` relative to the application, so `just bindist` builds (as
`just build`) in Make's BINDIR, `<app>/bin/<board>` (or `BINDIRBASE`/`BINDIR`
/`-B`), not in `just build`'s `<app>/bin/cmake-<board>`. With another BINDIR
the recipe does not find the products, as with Make.

Rule R3: what happens to Make's `bindist`
-----------------------------------------

`bindist` stays in Make, as `all` (G3-1) and `flash` (G3-2): every
application and board outside the data makes its distribution with make;
Make reads the generated adapter, so both read the same data, and the recipe
is unchanged (R3 test, line for line as in the base commit). For the scope
the entry point is `just bindist` (registered as target `bindist` of step
`g3-03-bindist`, no hardware). A request outside the data stops with exit 3
(BUILD_IN_DOCKER=1, a board or application without data such as native64,
building from a distribution: `Makefile.distcheck` in the application)
instead of falling back to make. `bindist` leaves Make when the data covers
every application and board.

Parity (2026-11-21, base 8324f6c5e9, golden file `tests/golden/`)
------------------------------------------------------------------

Golden file (`tests/record_golden.py`, a git checkout of the base, GNU Make
4.3, `env -i PATH HOME LC_ALL=C`, umask 022): per case `make -n -o all
bindist` (`-o all`: the build is the parity of G3-1) and, for the layout
cases, `make -o all bindist` on stand-in build products (an empty-content
file for each object of the build plan, the ELF and the binary; no
toolchain) with its output, the tree of `bindist/` (path, type, mode, size,
SHA-256, mtime kept or new) and `Makefile.distcheck`. The application is a
copy outside the tree (RIOTBASE on the command line; Make writes into the
application directory). Header with command, commit, date; last line
`## end`. Masked: paths (@RIOTBASE@, @APPDIR@, @TMP@), the computed
RIOT_VERSION and `git describe` (they name the checkout).

| nrf52840dk, examples/advanced/bindist | result |
|---|---|
| cases (default, `DIST_FILES='Makefile abc/abc.c'`, `RIOT_VERSION=9.9-test`, `BINDIRBASE` elsewhere, no build products) | 5 |
| commands = `make -n -o all bindist` (5 recipe lines, byte for byte) | 5/5 |
| distribution: output, success/failure, tree (9, 5, 9, 1 entries), Makefile.distcheck | 4/4 |
| live Make with the adapter = golden (commands and distribution) | 5/5 |
| live Make and bindist.py in this checkout, unmasked (version, git describe, tree with Makefile.distcheck content) | 2/2 |
| binaries (`make bindist` vs `just bindist`, real build) | skipped: needs arm-none-eabi-gcc (as G3-1 P5) |

Differences by design: Make's own line `make: *** [...bindist.inc.mk:N:
bindist] Error 1` and its exit status 2 for a failed command (bindist.py: 1);
`--no-build` reassembles an existing `bindist/` where `make -o all bindist`
would report it up to date (`make bindist` always runs the recipe, since
`all` is phony).

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/bindist/tests -v
dist/tools/migration/run_tests.py --step g3-03-bindist
```

49 tests in 5 modules (about 35 s, Make one at a time; 1 skipped without
arm-none-eabi-gcc).

| Rule | Test classes | How |
|---|---|---|
| D1 validator | `test_data.ValidatorTest` | the data file; 5 positive, 13 negative samples |
| D2 generator | `test_data.GeneratorTest` | exact Make text of the adapter and of `set`/`if` rules |
| D3 names | `test_data.NamesTest` | Make file, data, adapter; distribution data is no build or flash data |
| D4 adapters up to date | `test_data.AdaptersTest` | `generate --check`; missing, hand-edited, stale, invalid on a copy |
| D5 single source | `test_data.OwnerTest` | the owner includes its adapter first, assigns no DIST_FILES (detector samples) |
| D6 scope | `test_data.ScopeTest` | no Make file of the repository assigns DIST_FILES but the adapter and the generated application Makefile |
| A1-A5 algorithm | `test_algorithm.*` | read order and laziness; recipe text, `@`, command line DIST_FILES; running in the application directory, stop at the first failure, environment; exit 3 and 2; the build in Make's BINDIR, `-B`, BINDIRBASE, failed build |
| P1-P6 parity | `test_parity.*` | table above |
| N1-N4 no Make | `test_no_make.*` | audit-hook trace (5 cases x `--no-build`/`-n`); `just bindist` with stub make (never called) and stub cmake/ninja; a failed build makes no distribution; static check; just recipes without make (detector samples) |
| R1, R3, O1 | `test_transition.*` | `just --dry-run bindist`, parameters as `build`, Make keeps `bindist` with the recipe of the base commit, register entry |

Also changed: `dist/tools/config_data/tests/test_parity.py` (the live
MAKEFILE_LIST comparison of G0-1 ignores the new `*.dist.inc.mk` adapter),
`dist/tools/config_data/README.md` (distribution data), the justfile
(`bindist`, `generate-dist-data`), the register.

Mutation probe
--------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| D1 | validator accepts section/stand_in | bindist failures=4 |
| D2 | generator writes no header | bindist failures=4 |
| A1a | distribution data read after the build data | bindist failures=1 |
| A1b | distribution data not read | bindist failures=12 |
| A2a | $$ not reduced to $ (loop variable) | bindist failures=11 |
| A2b | recipe tab after backslash-newline kept twice | bindist failures=6 |
| A2c | binary taken from BINDIR, not bin/$(BOARD) | bindist failures=7 |
| A2d | cp -r instead of cp -a | bindist failures=12 |
| A3a | recipe runs in RIOTBASE, not the application directory (left bindist/ and env.txt in RIOTBASE, removed) | bindist failures=14, errors=1 |
| A3b | a failed line does not stop the recipe | bindist failures=4 |
| A3c | `@` not stripped | bindist failures=19 |
| A4 | BUILD_IN_DOCKER not refused | bindist failures=2 |
| A5 | build in bin/cmake-<board> instead of Make's BINDIR | bindist failures=4 |
| E1 | recipe environment without the exported variables | bindist failures=1, errors=1 |
| X1 | data: objects pattern *.a instead of *.o | bindist failures=21 |
| X2 | data: objects of BIN_USEMODULE dropped | bindist failures=16 |
| G1 | adapter edited by hand | bindist failures=8 |
| G2 | owner without the include of its adapter | bindist failures=7 |
| R3 | Make's recipe changed (cp -a -> cp -p for the binary) | bindist failures=7 |
| N1 | bindist.py starts `make --version` | bindist failures=13 |
| N2 | bindist.py opens Makefile.include | bindist failures=11 |
| R1 | just recipe calls make | bindist failures=3; task_layer failures=1 |
| O1 | register: bindist marked as hardware | bindist failures=1; migration failures=2 |

23/23 defects detected (2026-11-22; each file copied before the change,
restored from the copy and compared by SHA-256 afterwards; data mutations
regenerate the adapter, which is restored from its copy too; git status
unchanged).

Limits
------

* Scope: one application on nrf52840dk. Another application with
  DIST_FILES/BIN_USEMODULE needs its application data (G0-1); another board
  its build data (G3-1).
* Not converted (exit 3): BUILD_IN_DOCKER, building from a distribution
  (`Makefile.distcheck`, and with it `check_bindist`/`prepare_check_bindist`).
* The objects and the binary in the parity tests are stand-ins: their
  content needs the toolchain (P5, riotbuild image). The objects' names are
  those of the build plan, equal to Make's (G3-1 P1).
* Timestamps: compared as "kept from the source" or "new", not as values.
