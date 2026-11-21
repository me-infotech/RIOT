Build without Make: CMake + Ninja from data (migration step G3-1)
===================================================================

`just build <application> <board>` builds an application - what GNU Make's
target `all` does (ELF, binary, size) - with CMake and Ninja, from **data
only**: no make process, no Make file opened, no Make syntax parsed. Inputs
are the YAML data of the repository and the resolver of step G0-2
(`dist/tools/resolver`). Tool decision D24/D28: CMake with the Ninja
generator. Make keeps working unchanged for everything else.

```sh
just build examples/basic/hello-world nrf52840dk            # build dir: <app>/bin/cmake-nrf52840dk
just build examples/networking/gnrc/networking nrf52840dk WERROR=0 BUILD_DIR=/tmp/riot-build
dist/tools/cmake_gen/cmake_gen.py build -C <app> BOARD=<board> [-B <dir>] [-j 2] [VAR=VALUE…]
```

Scope: `examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on **nrf52840dk** (decision D22). Anything else
stops with exit status 3 and names the file that is not converted (e.g.
`BOARD=native64`: `boards/native64/Makefile.include` has no build data).

How it works
------------

```
riot-app.yaml ─┐  resolver (G0-2): modules, packages, features, CPU
deps.yaml …   ─┤
build.yaml,   ─┼─ plan.py ── plan.json ── emit.py ── riot-build.cmake ── cmake -G Ninja ── ninja
*.build.yaml  ─┤   (build algorithm)        compile_commands.json         (configure)
module.yaml   ─┤   toolchain.py (probes)
pkg.yaml      ─┘   pkg_prepare.py (packages: git, at configure time)
```

1. `cmake_gen.py generate` writes `<dir>/project/CMakeLists.txt`: a project
   without language (`LANGUAGES NONE`) that, at configure time, runs
   `cmake_gen.py plan` and includes the `riot-build.cmake` it writes. The
   data files are `CMAKE_CONFIGURE_DEPENDS`: a change of the data re-runs the
   generator on the next `ninja`.
2. `plan` resolves the application (G0-2), evaluates the build data, runs
   the toolchain probes, prepares the packages (like CMake's FetchContent, at
   configure time) and computes every command of `make all`.
3. `riot-build.cmake` has one `add_custom_command` per object (output,
   source, `DEPFILE` written by gcc's `-MD`, working directory = module
   directory as for `make -C`), the header steps, link, objcopy and size.
   The build directory is out of tree (`BINDIR` = CMake's binary directory).

Why custom commands and not CMake's C language support: RIOT's compile and
link lines are data (flags from the board, CPU, modules); CMake's language
model would rewrite them (full compiler path, its own object names and
dependency flags, de-duplication of options, working directory) and needs a
working compiler at configure time. With custom commands the commands are
RIOT's, word by word, so they can be compared with Make, and configuring
works without the toolchain. CMake still provides the build graph,
regeneration, out-of-tree builds, header dependencies (depfiles) and Ninja.
`compile_commands.json` is written by the generator.

Data model
----------

Everything the new build reads is YAML in the format of steps G0-1/G0-2
(`dist/tools/config_data/README.md`), **schema 3**. Schema 3 adds
(validator, generator, translator, normal form, evaluator; every schema 1/2
file stays valid):

| Construct | Meaning | Make (generated) |
|---|---|---|
| `{files: {match: [G…], except?: [P…]}}` | names that exist (relative to the module directory, each pattern sorted) | `$(filter-out P,$(wildcard G))` |
| `{subdirs: {select: SEL, file: F}}` | `word/` for each selected word with `word/F` | `$(dir $(wildcard $(addsuffix /F,SEL)))` |
| select `pattern: {from, to}` | pattern substitution | `$(patsubst from,to,…)` |
| select `macro: true` | `uppercase_and_underscore` | `$(call uppercase_and_underscore,…)` |
| select `unique: true` | duplicates removed, first kept (Makefile.include `uniq`) | build data only |
| `{arith: {expr, format?: dec\|hex}}` | `$((…))` of integers, `+ - * ()`, `NK` | build data only |
| condition `at_least: {var, version}` | `version_is_greater_or_equal` | `ifeq (1,$(call version_is_greater_or_equal,…))` |
| condition `nonempty: [VAR…]` | one of them is not blank | `ifneq (,$(A)$(B))` |

The files of the step (all new files are listed by `git status`):

| Kind | Files | Make file | Choice |
|---|---|---|---|
| module data | `module.yaml` in 87 module directories, `makefiles/periph.module.yaml`, `pkg/mpaland-printf/mpaland-printf.module.yaml`, `drivers/periph_common/module.yaml`; `makefiles/application.inc.yaml`, `makefiles/auto_init.inc.yaml` | **generated** from the YAML (`just generate-config-data`) | the Make file only describes the module build: one source, Make reads the adapter |
| build data | `build.yaml` next to 22 `Makefile.include`, `makefiles/*.build.yaml` (cflags, vars, git_version, bindist, default-radio-settings, pseudomodules, arch/cortexm, toolchain/gnu, libc/newlib), `pkg/pkg.build.yaml` | **generated** since step G0-3: the whole Make file, or its build part as `<data>.mk` that the Make file includes (scope.yaml `build`) | these Make files also hold what is not migrated yet (flashing, terminal, debugger, Docker, Kconfig); that part stays Make. The `$(shell)` probes are `makefiles/build_providers.inc.mk` for Make. The Doxygen documentation of `makefiles/pseudomodules.inc.mk` is kept in the data (`dist/tools/config_data/README.md`, step G0-3) |
| package data | `pkg/cmsis/pkg.yaml`, `pkg/mpaland-printf/pkg.yaml`, `cpu/nrf5x_common/nrfx.pkg.yaml` | **generated** part since step G0-3 (`pkg.mk`, `nrfx.pkg.mk`) | package Makefiles are recipes of `pkg/pkg.mk` (clone, patch); their values (URL, version, sparse paths, patches, build) are data |

Until step G0-3 the board, CPU and package Make files stayed unchanged next
to their data, a second source kept in agreement by the parity tests
(P1-P4); since G0-3 they are generated from the data: Make's commands are recorded in golden files and compared
with the commands computed from the data.

Names: `Makefile.include` → `build.yaml`, `<x>.inc.mk`/`<x>.mk` →
`<x>.build.yaml`, module `Makefile` → `module.yaml`, `<x>.mk` (module rules)
→ `<x>.module.yaml`, package `Makefile` → `pkg.yaml`, `Makefile.<x>` →
`<x>.pkg.yaml`. Build and package data are not found by their name like the G0-1 data;
scope.yaml `build` names the Make file of each (step G0-3).

Hand-written module data (scope.yaml `restructured`): the original
`drivers/periph_common/Makefile` and `makefiles/auto_init.inc.mk` built
their source lists with `$(subst)`/`$(addprefix)`/`$(addsuffix)`; the YAML
says the same with `pattern`. Their generated Make files give Make the same
commands (P4).

Algorithm, not data (`plan.py`, each function names the Make lines it
replaces): directories (`Makefile.include:67-77`), the order of the build
data (`build.yaml` follows `Makefile.include:209-1047`), Makefile.base
(sources, SUBMODULES, automatic sources, objects, compile command, DIRS
recursion), the exported variables of sub-makes (list in
`makefiles/vars.build.yaml`), modules.inc.mk (MODULE_* defines, real
modules), `version_tuple`, the package step (`pkg_prepare.py`, recipes of
`pkg/pkg.mk` and `Makefile.nrfx`), link (`find … | sort` = objects of the
linked modules sorted in byte order), binary, size, module check. Toolchain
probes (`toolchain.py`): the `$(shell …)` questions of the Make files
(compiler version, `-std=c11`, link tests, newlib nano, objcopy, git
describe) run the same commands and are read by the data as `PROBE_*`
variables; without the toolchain they give Make's answers.

Rule R3: what happens to Make's `all`
--------------------------------------

Rule R3 removes a migrated target from Make. `all` cannot be removed: every
application and board outside the scope still builds with it, and Make's
`flash`, `term`, … depend on it. Transitional rule:

* Make keeps `all` unchanged (`Makefile.include`: `all: link`) for all
  applications; its module Makefiles in scope are generated from the data,
  so both builds read the same module description.
* For the scope applications on nrf52840dk the documented entry point is
  `just build <app> <board>` (registered as target `all` of step
  `g3-01-all`); tests check that they build without Make (N1-N5) and with
  Make's commands (P1-P4).
* `all` leaves Make when the data covers every application and board (or the
  remaining ones are dropped); until then a request outside the data stops
  the build without Make with exit status 3 instead of falling back to Make.

Parity (2026-11-21, base commit 984ebddbbe, golden files `tests/golden/`)
--------------------------------------------------------------------------

Golden files: `make -n -k` of the base commit (git archive, unchanged), once
with an empty BUILD_DIR (package clone commands), once with prepared
packages and riotbuild.h (all build commands), and the headers Make
generates; header with command, commit, date, versions; last line `## end`
(`tests/record_golden.py`). arm-none-eabi-gcc is not installed on the
recording host, so the probes fail in Make and in the build without Make
alike (no `-std=c11`, no `-fdebug-prefix-map`, no `-z noexecstack`, host
`objcopy`).

Normalisation: paths → `@RIOTBASE@`, `@BUILD_DIR@`, `@BINDIR@`; RIOT_VERSION
masked (from `git describe`, names the checkout); commands compared as
argument vectors (Make's `\` continuations and blanks of empty variables);
the link's `$(find <module dirs> -name "*.o" | sort)` replaced by the
objects of Make's compile commands in those directories, sorted.

| nrf52840dk | hello-world | gnrc_networking | bindist |
|---|---|---|---|
| objects (Make = plan = Ninja) | 44 | 153 | 45 |
| compile command per object identical | 44/44 | 153/153 | 45/45 |
| link, objcopy, size identical | yes | yes | yes |
| riotbuild.h / preprocessor_successor.h commands identical | yes | yes | yes |
| riotbuild.h content (Ninja-built vs. Make-built, version masked) | identical | identical | identical |
| preprocessor_successor.h (SHA-256, 10016 lines) | identical | identical | identical |
| package clone commands (3 packages) | identical | identical | identical |
| live Make with the generated module Makefiles (P4) | = golden | = golden | = golden |

Differences that remain, by design:
* the riotbuild.h `sed` command: Make writes `1i\` with a line break
  inside the quotes, the build without Make uses GNU sed's one-line form
  `1i text`; the generated header is identical (P3);
* the dependency file: Make's `-MD -MQ` command is used unchanged; CMake is
  told the file name (`DEPFILE`), policy CMP0116 OLD keeps CMake from adding
  a `cmake -E cmake_transform_depfile` step (CMake prints a deprecation
  warning for it);
* packages are prepared at configure time (Make: before the first compile
  of every build); Make's timestamps of its own Make files are replaced by
  those of the package data files; the trailing blanks Make keeps in
  `PKG_VERSION` of pkg/cmsis are not part of the data;
* the version: from `git describe` in both builds (masked in the goldens).

Prepared package trees, opt-in test K3 (network, run on 2026-11-21): Make's
`fetch_nrfx_vendor_headers pkg-prepare` and `pkg_prepare.py` give the same
files for cmsis, mpaland-printf and the nRF vendor headers.

Firmware (P5): not run here - arm-none-eabi-gcc is not installed and no
toolchain or image is downloaded in this step. The test builds each
application with Make (`make all`) and with `cmake_gen.py build` and
compares the `.bin` byte by byte and `size -A`/`nm -n` of the ELF. Expected:
identical binaries (same commands, same order); the ELF files differ in the
debug sections only where paths differ (BINDIR of riotbuild.h, working
directory of the link). In CI, with the pinned riotbuild image (digest in
`makefiles/docker.inc.mk`, has the toolchain, make, git, cmake and ninja -
check `cmake --version` there first):

```sh
docker run --rm -v "$PWD":/data/riotbuild -w /data/riotbuild -e RIOT_G3_NETWORK=1 \
  docker.io/riot/riotbuild@sha256:<DOCKER_TESTED_IMAGE_REPO_DIGEST> \
  python3 -m unittest discover -s dist/tools/cmake_gen/tests -v
```

With the toolchain present the probes answer differently (e.g. `-std=c11`,
`-fdebug-prefix-map`, `-specs=nano.specs`), so P1, P2 and P4 skip with a
reason unless the goldens are recorded on a host with the toolchain
(`record_golden.py` inside the image; the header says which toolchain).

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/cmake_gen/tests -v
dist/tools/migration/run_tests.py --step g3-01-all
```

97 tests in 9 modules (about 16 s; 2 skipped without toolchain/network).

| Rule | Test classes | How |
|---|---|---|
| S1 schema 3 validator | `test_schema3.ValidatorTest` | 12 positive, 16 negative samples, schema 3 needed, schema 1/2 still valid |
| S2 generator | `test_schema3.GeneratorTest` | exact Make text per construct; build-only constructs refused |
| S3 translator | `test_schema3.TranslatorTest` | Make forms of the module Makefiles, round trip, unsupported forms stop |
| S4 names | `test_schema3.NamesTest` | module/build/package data names; build data is no adapter source |
| D1 data files | `test_schema3.DataFilesTest` | all 35 build/package files valid, each next to its Make file |
| E1-E4 evaluation | `test_evaluation.*` | `files`/`subdirs` (sorted, hidden, except, lazy), patsubst/macro/unique, arith, `at_least`/`nonempty`, providers lazy and once, include → build data, LAST_MAKEFILEDIR, unconverted Make file → OutOfScope |
| A1-A5 algorithm | `test_algorithm.*` | Makefile.base (auto sources, SUBMODULES, NO_AUTO_SRC, SRC_NOLTO, LTO, static analysis, DIRS), DIRS recursion with exported variables only, MODULE_* defines, real modules, version tuple, link order (C locale), module check, headers |
| T1-T2 probes | `test_toolchain.*` | stub toolchain on PATH: Make's commands and answers; no toolchain: Make's answers |
| G1-G2 CMake code | `test_emit.*` | quoting, per-object custom command with DEPFILE and working directory, headers, link, reconfigure on data change, project runs the generator |
| K1-K3 packages | `test_pkg_prepare.*` | clone commands = Make's (goldens); local repository: fetch, patch, copy, states, up to date, re-patch, re-clone, CI apply, failure, removal only inside BUILD_DIR; K3 (opt-in) same trees as Make |
| P1-P5 parity | `test_parity.*` | table above; P5 opt-in with toolchain |
| N1-N5 no Make | `test_no_make.*` | audit-hook trace of the generator (3 apps) and of the Python processes CMake/Ninja start; stub `make`/`gmake` on PATH never called; CMake's make program is ninja; generated files without make call (detector with positive and negative samples); only toolchain/pkg_prepare/cmake_gen start processes, no module names make |
| R1, R3 | `test_transition.*` | `just --dry-run build`, recipe parameters, Make keeps `all`, register entry, outside the data → exit 3 |
| O1 register | `dist/tools/migration/tests` | step `g3-01-all` (group 3, target `all`, hardware false) |

Also changed for the step: `dist/tools/config_data` (schema 3, module data,
scope.yaml `modules`/`restructured`; its tests: schema number and one
message), `dist/tools/resolver/variables.py`/`evaluate.py` (evaluation of the
schema 3 constructs), the justfile (`build`). Their suites stay green
(config_data 79, resolver 67, migration 27, task_layer 18).

Mutation probe (each file copied before the change, restored from the copy)
---------------------------------------------------------------------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| S1 | validator accepts any file pattern | cmake_gen 1 |
| S2 | generator swaps the patsubst arguments | cmake_gen 3, config_data 2 |
| S3 | translator drops the `except` of a wildcard | cmake_gen 2, config_data 5 |
| E1 | wildcard not sorted | cmake_gen 8 failures, 6 errors |
| E2 | patsubst replaces words that do not match | cmake_gen 1 |
| E3 | `at_least` strictly greater | cmake_gen 2 |
| A1 | SUBMODULES ignored | cmake_gen 9 |
| A2 | sub-makes get every variable, not only the exported ones | cmake_gen 4 failures, 10 errors |
| A4 | link objects not sorted | cmake_gen 8 |
| A5 | module check off | cmake_gen 1 |
| T1 | probe `-std=c11` always succeeds | cmake_gen 10 |
| G1 | no DEPFILE for objects | cmake_gen 1 |
| G2 | object command without working directory | cmake_gen 1 |
| K1 | clone without `--depth=1` | cmake_gen 9 |
| K2 | patches not applied | cmake_gen 3 |
| D1 | build.yaml: `-Werror` replaced | cmake_gen 7 |
| D2 | cortexm.build.yaml: `-Os` -> `-O2` | cmake_gen 7 |
| D3 | pkg/cmsis/pkg.yaml: other version | cmake_gen 3 |
| D4 | sys/ztimer/module.yaml without util.c, Makefile regenerated | cmake_gen 4 (incl. live Make P4), config_data 2 |
| N1 | generator starts `make --version` (probe) | cmake_gen 12 |
| N2 | generator opens Makefile.include | cmake_gen 3 |
| R1 | just recipe calls make | cmake_gen 2, task_layer 1 |
| O1 | register: `all` marked as hardware | cmake_gen 2, migration 2 |

23/23 defects detected (2026-11-21; each file restored from its copy, compared byte by byte afterwards; the regenerated sys/ztimer/Makefile regenerated again from the restored YAML).

Limits
------

* Scope: three applications on nrf52840dk. Another board, CPU, module or
  package needs its build/module/package data (the files are named in the
  error). native64 is not converted (D22).
* Not part of the data (stop with exit 3 when used): C++, assembler,
  generated sources, blobs, ARCHIVES, LTO is computed but untested, Kconfig,
  riotboot/MCUboot images, git-cache-rs, PKG_SOURCE_LOCAL, CMSIS-DSP/NN,
  llvm, binary distributions (Makefile.distcheck), `EVENT_THREAD_*_STACKSIZE_MIN`.
* The firmware comparison needs arm-none-eabi-gcc (P5, CI image); the
  goldens were recorded without it.
* Make's `..compiler-check` and `..build-message` are not reproduced (a
  missing compiler fails at the first compile).
* The link order equals `find | sort` in the C locale (as the goldens);
  Make in another locale may order differently.
