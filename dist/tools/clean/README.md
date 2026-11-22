Clean without Make: clean data (migration step G2C-1)
=====================================================

`just clean <application> <board>` removes what GNU Make's target `clean`
of an application removes and, in addition, the build directory of the
build without Make (`just build`, `just flash`). Inputs are **data only**:
the YAML data of the repository, the resolver (G0-2), the build and package
data (G3-1) and the clean data of this step. No make process is started, no
Make file is opened, no Make syntax is parsed.

```sh
just clean examples/basic/hello-world nrf52840dk
just clean examples/basic/hello-world nrf52840dk -B /path/below/a/root   # build dir of `just build -B`
dist/tools/clean/clean.py clean -C <app> BOARD=<board> [-B <dir>] [-n] [VAR=VALUE…]
```

`-n` prints the commands (as `make -n clean`, without the sub-make lines).
Exit status: 0 (a failing command is reported and ignored, as Make's `-`);
2 an error of the configuration; 3 the request is outside the data; 4 a
path is refused by the safety rules, nothing is removed.

Scope: `examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on **nrf52840dk** (decision D22). `clean-pkg`,
`clean-intermediates` and the root Makefile's `clean`, `distclean` and
`pkg-clean` are other targets and not part of this step; the application's
`distclean` is step G2C-2 (section [distclean](#distclean-step-g2c-2) below).

What Make's `clean` does (base 74a0fb9743)
-------------------------------------------

`Makefile.include:605-611`, run in the application directory:

```make
clean:
ifndef MAKE_RESTARTS
	-@$(foreach dir,$(PKG_PATHS),"$(MAKE)" -C $(dir) clean $(NEWLINE))
	-@rm -rf $(BINDIR)
	-@rm -rf $(SCANBUILD_OUTPUTDIR)
endif
```

and in every package of PKG_PATHS (sub-make with the exported and command
line variables) the rule of `pkg/pkg.mk:178-185`:

```make
ifeq ($(PKG_SOURCE_DIR),$(PKG_BUILD_DIR))
clean::
	@-test -d $(PKG_SOURCE_DIR) && $(GIT_IN_PKG) clean -xdff '**' -e $(PKG_STATE:$(PKG_SOURCE_DIR)/%='%*')
else
clean::
	rm -rf $(PKG_BUILD_DIR)
endif
```

For the scope (`make -n clean`, all three applications alike):

| # | Command | Where it comes from | Value |
|---|---|---|---|
| 1 | `rm -rf $(PKG_BUILD_DIR)` of pkg/cmsis (printed) | pkg.mk:184, `PKG_BUILD_DIR ?= $(BINDIR)/pkg-build/$(PKG_NAME)` (pkg.build.yaml) | `<app>/bin/nrf52840dk/pkg-build/cmsis` |
| 2 | the same for pkg/mpaland-printf (printed) | as 1 | `<app>/bin/nrf52840dk/pkg-build/mpaland-printf` |
| 3 | `rm -rf $(BINDIR)` | Makefile.include:608; BINDIR: directories (G3-1) | `<app>/bin/nrf52840dk` |
| 4 | `rm -rf $(SCANBUILD_OUTPUTDIR)` (relative to the application) | Makefile.include:609; clean data | `scan-build/nrf52840dk` |

PKG_PATHS (`dependency_resolution.inc.mk`, the resolver) holds
`pkg/cmsis/` and `pkg/mpaland-printf/`; the nRF vendor headers
(`Makefile.nrfx`, BUILD_PACKAGES) are no PKG_PATHS entry and are not
cleaned. An in-source package (`PKG_BUILD_OUT_OF_SOURCE=0`: PKG_SOURCE_DIR =
PKG_BUILD_DIR = `$(BINDIR)/pkg/<name>`) runs `git clean -xdff` there, keeping
the `.pkg-state.git*` files. Make's clean keeps: the prepared packages in
BUILD_DIR (`build/pkg/…`, removed by `distclean`), the distribution
`bindist/` of `make bindist`, other boards' BINDIRs and scan-build reports.

Mapping to the build without Make
---------------------------------

| Produced by | Where | Removed by |
|---|---|---|
| `just build`, `just flash` (CMake + Ninja; objects, ELF, binaries, `riotbuild/`, `project/`, CMake and Ninja files, `plan.json`, `compile_commands.json`, the J-Link `burn.seg`) | `<app>/bin/cmake-<board>` (`cmake_gen.py builddir()`, `-B`) | `rm -rf` of that directory (the `build` part of the plan; Make does not know it) |
| `just bindist` (build in Make's BINDIR) | `<app>/bin/<board>` | command 3, as for Make |
| packages built in BINDIR (pkg-build) | `<BINDIR>/pkg-build/<name>` | commands 1-2 |
| package step (`pkg_prepare.py`, as Make's pkg-prepare) | `BUILD_DIR/pkg/<name>`, `BUILD_DIR/nrf5x_nrfx_mdk/…`, `CACHEDIR.TAG` | kept (as Make's clean) |
| `just bindist` distribution | `<app>/bindist/` | kept (as Make's clean) |

`just clean` = Make's commands 1-4 (in Make's order, with Make's output:
the two package lines are printed) + `rm -rf <app>/bin/cmake-<board>`. When
the build directory is Make's BINDIR or inside it, the extra command is
dropped.

Data model
----------

The one setting of `clean` that was not data yet - the directory of the
scan-build reports, `SCANBUILD_OUTPUTDIR = scan-build/$(BOARD)` in
`makefiles/scan-build.inc.mk` - is a rule list next to it, the **single
source**; `scan-build.inc.mk` includes the adapter generated from it
(`just generate-clean-data`, private recipe; `clean.py generate --check` in
the tests) as its first statement and no longer assigns the variable:

| Make file | clean data | adapter (generated) | content |
|---|---|---|---|
| `makefiles/scan-build.inc.mk` | `scan-build.clean.yaml` | `scan-build.clean.inc.mk` | `SCANBUILD_OUTPUTDIR = scan-build/$(BOARD)` |

Format: `{schema: 3, rules}` with the rule language of
`dist/tools/config_data/README.md` without the build-only constructs
`section` and `stand_in` (validator and generator in `cleandata.py`, as the
distribution data of G3-3). The value stays recursive, so a command line
value replaces it and BOARD is read when it is used, as before. Already data
before this step: BINDIR and the other directories (G3-1), PKG_PATHS (the
resolver, G0-2), PKG_SOURCE_DIR/PKG_BUILD_DIR/PKG_BUILD_OUT_OF_SOURCE
(`pkg/pkg.build.yaml`, G0-3), the packages' names (`pkg.yaml`).

Algorithm, not data (`clean.py`, each part names the Make lines it
replaces): the read order (the clean data where Makefile.include:211
includes scan-build.inc.mk, before build.yaml), the recipe of
Makefile.include:605-611 (order, the application directory as working
directory, Make's `-`: failures ignored), the package rule of
pkg/pkg.mk:178-185 (the state file name `.pkg-state.git` of pkg.mk), the
build directory of `just build` (the function of cmake_gen.py, single
source), and the safety rules. The commands run without a shell (`rm -rf
<path>`, `git … clean …` as argument vectors); S1 makes this the same as
Make's shell line.

Safety rules
------------

`clean` refuses (exit 4, "refused: …", nothing removed) when one path of the
plan breaks a rule; all paths are checked before the first is removed.

| Rule | A path (`rm -rf` target or `git clean` directory) must |
|---|---|
| S1 | be one plain word (`[A-Za-z0-9_./+,@%=:-]`), no `..` component: no blank, quote, glob, `$`, `;` that the shell would expand |
| S2 | lie strictly below a root: `<app>/bin`, `BINDIRBASE`, `<app>/scan-build`, `BUILD_DIR` (RIOT's build directory); a root that is `/`, `$HOME`, RIOTBASE, the application directory or above one of them is dropped |
| S3 | not leave its root through a symbolic link below it (the real path of its parent stays below the root's real path); a link that is the path itself is removed, not followed (`rm -rf`) |
| S4 | be checked with all others before anything runs (`-n` refuses as well) |

Make's `clean` follows BINDIR, BINDIRBASE and SCANBUILD_OUTPUTDIR anywhere
(`make clean BINDIRBASE=/` would run `rm -rf //nrf52840dk`); `just clean`
refuses such values. Deliberate differences: refused paths (exit 4); a
failing command is reported as `clean: \`…\` (origin) failed …` instead of
Make's `make: [file:line: clean] Error N (ignored)`.

Rule R3: what happens to Make's `clean`
---------------------------------------

`clean` stays in Make: every application and board outside the data cleans
with make (R3 test: the recipes of Makefile.include and pkg/pkg.mk are those
of the base commit, line for line; `make -n clean BOARD=native64` works).
Make reads the generated adapter, so both read the same data. For the scope
the entry point is `just clean` (registered as target `clean` of step
`g2c-01-clean`, group 2C, no hardware). A request outside the data stops
with exit 3 instead of falling back to make: a board or application without
data (native64), a package without package data, `PKG_SOURCE_LOCAL` (the
clean of `pkg/local.mk`). `BUILD_IN_DOCKER=1` is no reason: Make's `clean`
runs on the host as well. `clean` leaves Make when the data covers every
application and board.

Parity (2026-11-22, base 74a0fb9743, golden file `tests/golden/`)
-----------------------------------------------------------------

Golden file (`tests/record_golden.py`, a git checkout of the base, GNU Make
4.3, `env -i PATH HOME LC_ALL=C GIT_ALLOW_PROTOCOL=file`, umask 022):
`make -n clean` for 7 cases, and for each application a tree case: `make -j1
all` (`bindist` for the bindist application) with a stub toolchain and
stand-in prepared packages in `BUILD_DIR` (state files of pkg.mk newer than
every input: no git, no network), stand-ins of what must go or stay
(`scan-build/<board>`, `scan-build/native64`, `bin/native64`,
`bin/cmake-native64`), `make clean`: its output and the file list (path,
type) of the application copy and BUILD_DIR. Application copies outside the
tree, RIOTBASE and BUILD_DIR on the command line; header with command,
commit, date; last line `## end`. Paths masked as @RIOTBASE@, @APPDIR@,
@TMP@. Make's sub-make lines (`"make" -C <pkg> clean`) name the package of
the commands that follow; the comparison keeps that pairing.

| nrf52840dk | result |
|---|---|
| `make -n clean` cases (hello-world, gnrc_networking, bindist; SCANBUILD_OUTPUTDIR, BINDIRBASE elsewhere, in-source packages, BUILD_IN_DOCKER) | 7 |
| plan = `make -n clean` (commands with their package, in order) | 7/7 |
| `clean.py -n` = Make's commands + `rm -rf <app>/bin/cmake-nrf52840dk` | 7/7 |
| tree: `just build` (+ `just bindist`) + `just clean` = `make all` (`bindist`) + `make clean`: output, file list (71, 72, 85 entries) | 3/3 |
| build products before clean (Make: 93, 311, 95 files in bin/nrf52840dk; `just build`: > 50 in bin/cmake-nrf52840dk) | 3/3 |
| live Make with the adapter: `make -n clean` = golden | 7/7 |
| live `make clean` on the tree of `just build`: golden tree + exactly `bin/cmake-nrf52840dk` | 1/1 |

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/clean/tests -v
dist/tools/migration/run_tests.py --step g2c-01-clean
```

52 tests in 5 modules (about 35 s; make, just, cmake, ninja, git; one
build at a time with `-j 1`).

| Rule | Test classes | How |
|---|---|---|
| D1 validator | `test_data.ValidatorTest` | the data file; 5 positive, 13 negative samples |
| D2 generator | `test_data.GeneratorTest` | exact Make text of the adapter and of `set`/`if` rules |
| D3 names | `test_data.NamesTest` | Make file, data, adapter; clean data is no build, flash or distribution data |
| D4 adapters up to date | `test_data.AdaptersTest` | `generate --check`; missing, hand-edited, stale, invalid on a copy |
| D5 single source | `test_data.OwnerTest` | the owner includes its adapter first, assigns no SCANBUILD_OUTPUTDIR (detector samples) |
| D6 scope | `test_data.ScopeTest` | no Make file assigns SCANBUILD_OUTPUTDIR but the adapter; every clean data file is read |
| A1-A6 algorithm | `test_algorithm.*` | read order, recursive value, command line; order, commands, printed lines, origins, working directories; in-source `git clean` on a real repository (untracked gone, state files kept, skipped without the directory); package without data; build directory default/-B/in BINDIR; removes exactly the plan; failure ignored; `-n`; exit 3 and 2 |
| S1-S4 safety | `test_algorithm.SafetyTest` | 7 non-plain words, 10 values and 5 `-B` outside the roots, the roots themselves, accepted roots, a symbolic link out of a root (and a link as the path), one refusal removes nothing, `-n` refuses |
| P1-P5 parity | `test_parity.*` | table above |
| N1-N4 no Make | `test_no_make.*` | audit-hook trace (7 cases x `-n`/run, processes: rm, git, toolchain probes only); `just clean` with stub make (never called); static check; just recipes without make (detector samples) |
| R1, R3, O1 | `test_transition.*` | `just --dry-run clean`, parameters as `build`, Make keeps `clean` with the recipes of the base commit and cleans native64 (clean.py: exit 3), register entry |

Also changed: `dist/tools/config_data/tests/test_parity.py` (the live
MAKEFILE_LIST comparison of G0-1 ignores the new `*.clean.inc.mk` adapter),
`dist/tools/config_data/README.md` (clean data), the justfile (`clean`,
`generate-clean-data`), the register.

Mutation probe
--------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| D1 | validator accepts section/stand_in | clean failures=5 |
| D2 | generator writes no header | clean failures=4 |
| A1 | clean data not read | clean failures=38 |
| A2a | packages cleaned in reverse order | clean failures=21 |
| A2b | package clean line not printed | clean failures=5 |
| A2c | scan-build reports removed relative to RIOTBASE | clean failures=34 |
| A3a | in-source package: rm -rf of the source directory instead of git clean | clean failures=3, errors=1 |
| A3b | git clean keeps .pkg-state* instead of .pkg-state.git* | clean failures=1 |
| A4 | build directory of just build not removed | clean failures=33 |
| A5 | one path too many: also Make's BINDIR of another board (bin/native64) | clean failures=20 |
| A6 | a failing command stops clean (exit 1) | clean failures=1 |
| S1 | S1 off: any word accepted | clean failures=6 |
| S2 | S2: the home directory may be a root | clean failures=3 |
| S3 | S3 off: symbolic links not checked | clean failures=1 |
| S4 | S4: the first command runs before the check | clean failures=6 |
| X1 | data: scan-build instead of scan-build/${BOARD} (adapter regenerated) | clean failures=46 |
| G1 | adapter edited by hand | clean failures=8 |
| G2 | owner without the include of its adapter | clean failures=8 |
| R3 | Make's recipe changed (rm -rf $(BINDIR)/*) | clean failures=8 |
| N1 | clean.py starts make --version | clean failures=16 |
| N2 | clean.py opens Makefile.include | clean failures=15 |
| R1 | just recipe calls make | clean failures=6; task_layer failures=1 |
| O1 | register: clean marked as hardware | clean failures=1; migration failures=2 |

23/23 defects detected (2026-11-22; each file copied before the change,
restored from the copy and compared by SHA-256 afterwards; X1 regenerates
the adapter, which is restored from its copy too; run with HOME set to a
temporary directory, so S2 and S4 could not reach the real home directory).

Limits
------

* Scope: three applications on nrf52840dk; another board or application
  needs its build data (G3-1) and application data (G0-1).
* Not converted (exit 3): PKG_SOURCE_LOCAL (`pkg/local.mk`); packages with
  their own `clean::` rules (c25519, cryptoauthlib, driver_cryptocell_310,
  jerryscript, picosdk) have no package data yet. git-cache-rs stops the
  evaluation of the package data as in G3-1 (exit 2), although Make's clean
  does not use it.
* Refused (exit 4) where Make would remove: BINDIR outside BINDIRBASE and
  `<app>/bin`, BINDIRBASE or BUILD_DIR at `/`, `$HOME`, RIOTBASE or the
  application directory, paths with blanks or shell characters.
* The tree comparison uses a stub toolchain and stand-in packages: the file
  names are the build's (G3-1 P1 for the commands), the contents are not
  compared (irrelevant to `clean`). `just flash` is not run in the tree
  test; its only extra output (`burn.seg` of J-Link) is in the build
  directory.

distclean (step G2C-2)
======================

`just distclean <application> <board>` removes what GNU Make's target
`distclean` of the application removes and, like `just clean`, the build
directory of `just build` when it is not below BINDIRBASE. Same tool, same
inputs, same exit status as `clean` (0, 2, 3, 4); no make process, no Make
file, no Make syntax.

```sh
just distclean examples/basic/hello-world nrf52840dk
just distclean examples/basic/hello-world nrf52840dk -B /path/below/a/root
dist/tools/clean/clean.py distclean -C <app> BOARD=<board> [-B <dir>] [-n] [VAR=VALUE…]
```

What Make's `distclean` does (base 74a0fb9743)
----------------------------------------------

`Makefile.include:624-626`, in the application directory, and in every
package of PKG_PATHS (sub-make) the rules of `pkg/pkg.mk:177-188`:

```make
distclean:
	-@$(foreach dir,$(PKG_PATHS),"$(MAKE)" -C $(dir) distclean $(NEWLINE))
	-@rm -rf $(BINDIRBASE)

distclean:: clean                # pkg/pkg.mk: clean:: as for `clean`
	rm -rf $(PKG_SOURCE_DIR)
```

For the scope (`make -n distclean`, all three applications alike):

| # | Command | Printed | Value |
|---|---|---|---|
| 1 | `rm -rf $(PKG_BUILD_DIR)` of pkg/cmsis (its `clean::`) | yes | `<app>/bin/nrf52840dk/pkg-build/cmsis` |
| 2 | `rm -rf $(PKG_SOURCE_DIR)` of pkg/cmsis (pkg.mk:188, `PKG_SOURCE_DIR ?= $(PKGDIRBASE)/$(PKG_NAME)`) | yes | `BUILD_DIR/pkg/cmsis` |
| 3-4 | the same for pkg/mpaland-printf | yes | |
| 5 | `rm -rf $(BINDIRBASE)` | no | `<app>/bin` (every board, also `bin/cmake-<board>` of `just build`) |

`distclean` does not depend on `clean`: the scan-build reports
(`scan-build/<board>`), the distribution `bindist/`, other packages in
`BUILD_DIR/pkg`, the sparse files (`build/pkg/cmsis.sparse`), the nRF vendor
headers (`BUILD_DIR/nrf5x_nrfx_mdk`) and `CACHEDIR.TAG` stay. An in-source
package runs its silent `git clean` (as for `clean`) and then `rm -rf` of the
source directory. The package sources are shared by all applications: as
with Make, the next build of any application prepares them again.

Make's error handling, which `distclean` makes visible: every line of a
package's sub-make is without `-`, so a failing line (e.g. `rm -rf` of a
directory it cannot empty) ends that sub-make - the package's source stays
- and the top level ignores it (`-@`) and goes on with the next package and
BINDIRBASE; exit status 0.

Implementation (`clean.py`, no new module, no duplicated logic)
---------------------------------------------------------------

| Part | Make lines | Shared with `clean` |
|---|---|---|
| evaluation (`evaluate`) | Makefile.include, resolver, build data | the same function |
| `packages_part(ev, goal)` | the foreach of Makefile.include:607/625 | the same function, goal `clean`/`distclean` |
| `package_part(…, goal)` | pkg/pkg.mk:178-188: the `clean::` entries, then for `distclean` `rm -rf $(PKG_SOURCE_DIR)` | the `clean::` entries are those of `clean` (test) |
| `distclean_part` | Makefile.include:624-626 | - |
| `build_part` | the build directory of `just build`, dropped below BINDIRBASE | the same function |
| `refusals`, `run` | safety; Make's `-` and the end of a failing sub-make | the same functions (`clean` has one line per package, so its behaviour is unchanged) |

Data: nothing new. Every value is data or algorithm of an earlier step:
BINDIRBASE, PKGDIRBASE, BUILD_DIR (directories, G3-1), PKG_PATHS (resolver,
G0-2), PKG_SOURCE_DIR/PKG_BUILD_DIR/PKG_BUILD_OUT_OF_SOURCE
(`pkg/pkg.build.yaml`, G0-3), the clean data of G2C-1 (read by the shared
evaluation). No Make file changes, so no adapter is needed.

Safety
------

The rules S1-S4 of `clean` apply to every path of the plan; distclean adds
PKGDIRBASE to the roots of S2 (the package sources lie below it) and one
rule for the path that is a root itself:

| Rule | |
|---|---|
| S1-S4 | as for `clean` (plain words; below a root - `<app>/bin`, BINDIRBASE, `<app>/scan-build`, BUILD_DIR, **PKGDIRBASE**; no symbolic link out of a root; all checked before anything runs, `-n` refuses as well) |
| S5 | BINDIRBASE itself (Makefile.include:626) is removed only when it is a root (S2: not `/`, `$HOME`, RIOTBASE, the application directory or above one of them) and not a directory directly below `/` (`BINDIRBASE=/usr`, `/opt`: refused) |

Make's `distclean` runs `rm -rf $(BINDIRBASE)` for any value
(`make distclean BINDIRBASE=$HOME` removes the home directory);
`just distclean` refuses with exit 4 and removes nothing.

Root `distclean` (stays in Make, unchanged)
-------------------------------------------

The root Makefile's `distclean` (`docclean _pkg-clean DISTCLEAN--<dir>…`,
step G2C-3) runs `make -C <dir> distclean` in every application and tool
directory (746 directories), without BOARD: the default board native64,
outside the data. It therefore keeps calling Make's application-level
`distclean`, which stays in Make (R3) for all applications and boards
outside the data; calling just for the three scope applications would only
apply for BOARD=nrf52840dk and would duplicate the iteration. Nothing of the
root Makefile changes; the test compares its `make -n distclean` (sub-makes
replaced by `echo`) with the Makefiles of 74a0fb9743 and 9cd0952bc7: equal,
all directories (the three scope applications included) iterated.

R3: Make keeps the application's `distclean` (recipes of Makefile.include and
pkg/pkg.mk line for line as in the base commits, `make -n distclean` works
for native64, where `clean.py distclean` stops with exit 3). It leaves Make
when the data covers every application and board.

Parity (2026-11-22, base 74a0fb9743, `dist/tools/distclean/tests/golden/`)
--------------------------------------------------------------------------

Golden file (`record_golden.py`, git checkout of the base, GNU Make 4.3,
`env -i PATH HOME LC_ALL=C GIT_ALLOW_PROTOCOL=file`, umask 022): `make -n
distclean` for 8 cases and 4 tree cases with the sample of G2C-1 (stub
toolchain, stand-in prepared packages in BUILD_DIR, no network) plus
stand-ins that must stay (`scan-build/…`, `BUILD_DIR/pkg/other-package`) or
go (`bin/native64`, `bin/cmake-native64`); `hello-world-locked` adds a
directory of mode 0555 below `pkg-build/cmsis`. Header with command,
commit, date, last line `## end`.

| nrf52840dk | result |
|---|---|
| `make -n distclean` cases (hello-world, gnrc_networking, bindist; BINDIRBASE, PKGDIRBASE, BUILD_DIR elsewhere, in-source packages, BUILD_IN_DOCKER) | 8 |
| plan = `make -n distclean` (commands with their package, in order); build part empty, `rm -rf <app>/bin/cmake-nrf52840dk` with BINDIRBASE elsewhere | 8/8 |
| `clean.py distclean -n` = Make's commands + build part | 8/8 |
| tree: `just build` (+ `just bindist`) + `just distclean` = `make all` (`bindist`) + `make distclean`: exit status, output, file list (60, 61, 74 entries) | 3/3 |
| failing sub-make (`-locked`): exit status 0, file list (71 entries: the cmsis sources stay), output without Make's diagnostics | 1/1 |
| build products before distclean (Make: 93, 311, 95 files; `just build`: > 50 in bin/cmake-nrf52840dk) | 3/3 |
| live Make in this checkout: `make -n distclean` = golden | 8/8 |
| live `make distclean` on the tree of `just build` = golden tree | 1/1 |
| root `make -n distclean` = the Makefiles of both bases | 2/2 |

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/distclean/tests -t dist/tools/distclean/tests -v
dist/tools/migration/run_tests.py --step g2c-02-distclean
```

37 tests in 5 modules (about 40 s; make, just, cmake, ninja, git; one build
at a time with `-j 1`). The test helpers (`dsample.py`) build on the sample
of G2C-1; the no-Make detectors are those of G2C-1.

| Rule | Module | How |
|---|---|---|
| A1-A7 | `test_distclean_algorithm` | order, commands, printed lines, origins, working directories, `ignore`; the package lines of distclean are those of clean plus the source; in-source `git clean` then `rm -rf` on a real repository; build part (default, -B, BINDIRBASE elsewhere); removes exactly the plan; a failing package line ends its sub-make, a failing top-level line is ignored; `-n`; exit 3, 2 and argument errors |
| S1-S5 | `test_distclean_safety` | 10 non-plain words, 11 values and 5 `-B` outside the roots, accepted roots, a symbolic link out of BUILD_DIR (and BINDIRBASE as a link), one refusal removes nothing, `-n` refuses, BINDIRBASE directly below `/`; values naming system or home directories run only with `-n` |
| P1-P5 | `test_distclean_parity` | table above |
| N1-N4 | `test_distclean_no_make` | audit-hook trace (8 cases x `-n`/run: no Make file, no make; processes rm, git, toolchain probes), `just distclean` with a stub make (never called), static check, recipe without make (probes of every detector) |
| R1, R3, R4, O1 | `test_distclean_transition` | `just --dry-run distclean`, parameters as `build`/`clean`; Make's recipes as in both bases, native64 with make (clean.py: exit 3); root `distclean`; register entry |

Deliberate differences
----------------------

* Refused paths (exit 4, S1-S5) where Make would remove.
* Diagnostics of a failing line: `distclean: \`…\` (origin) failed with exit
  status N…` instead of Make's `make[1]: *** […] Error N` and `make: […]
  Error N (ignored)`; the commands, rm's own messages, the effect and the
  exit status are Make's (tree case `-locked`).
* Inherited from `clean`: an in-source package whose directory is missing
  is skipped silently, where Make prints `make[1]: [pkg.mk:181: clean] Error
  1 (ignored)`.
* `just distclean` also removes the build directory of `just build` when it
  is not below BINDIRBASE (`-B`, BINDIRBASE elsewhere); Make does not know
  it.

Mutation probe (distclean)
--------------------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| A1a | BINDIRBASE not removed | distclean failures=35; clean OK |
| A1b | one package skipped (first of PKG_PATHS) | distclean failures=32; clean OK |
| A1c | one path too many: also the scan-build reports | distclean failures=23; clean OK |
| A1d | BINDIRBASE removed before the packages | distclean failures=19; clean OK |
| A2a | package source not removed | distclean failures=45; clean OK |
| A2b | package source line not printed | distclean failures=6; clean OK |
| A2c | in-source: git clean dropped for distclean | distclean failures=4; clean OK |
| A3a | build directory removed although below BINDIRBASE | distclean failures=17; clean OK |
| A3b | build directory never removed | distclean failures=8; clean OK |
| A5 | failing package line does not end its sub-make | distclean failures=2; clean OK |
| S2 | PKGDIRBASE no root | distclean failures=6; clean OK |
| S5a | S5 off: BINDIRBASE removed as a whole without checks | distclean failures=5; clean OK |
| S5b | S5: directories below / allowed | distclean failures=4; clean OK |
| S4 | distclean: first command runs before the check | distclean failures=6; clean OK |
| N1 | distclean starts make --version | distclean failures=18; clean failures=1 |
| N2 | distclean opens Makefile.include | distclean failures=17; clean OK |
| R1 | just recipe calls make | distclean failures=6 |
| R3 | Make's application distclean changed (rm -rf $(BINDIR)) | distclean failures=12 |
| R4 | root distclean: sub-make goal clean | distclean failures=2 |
| O1 | register: distclean marked as hardware | distclean failures=1 |
| G1 | golden: one package line dropped from the tree output | distclean failures=1 |

21/21 defects detected (2026-11-22; each file copied before the change,
restored from the copy and compared by SHA-256 afterwards; HOME set to a
temporary directory; the distclean tests, for clean.py also the clean tests).

Limits
------

* Scope and exit 3 as for `clean` (three applications on nrf52840dk,
  PKG_SOURCE_LOCAL, packages without package data).
* Packages with their own `distclean::`/`clean::` rules (c25519,
  cryptoauthlib, driver_cryptocell_310, jerryscript, picosdk) have no
  package data (exit 3).
* The tree comparison uses the stub toolchain and stand-in packages of
  G2C-1; real package sources (git checkouts) are not downloaded.
