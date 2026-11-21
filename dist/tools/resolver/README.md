Resolver without Make (migration step G0-2)
===========================================

`resolver.py` computes what Make's dependency resolution computes for an
application and a board - modules, packages, used/missing/provided
features, the CPU and its data - from **data only**: it reads YAML files,
never opens a Make file and never runs `make`. Make keeps working
unchanged through the Make files generated from the same YAML (step G0-1,
`dist/tools/config_data`).

```sh
dist/tools/resolver/resolver.py -C examples/basic/hello-world BOARD=nrf52840dk info-modules
dist/tools/resolver/resolver.py -C <app> BOARD=<board> info-packages info-features-used \
    info-features-missing info-features-provided info-cpu
dist/tools/resolver/resolver.py -C <app> BOARD=<board> info-debug-variable-CPU_MODEL
dist/tools/resolver/resolver.py -C <app> BOARDS="nrf52840dk native64" info-boards-supported
dist/tools/resolver/resolver.py -C <app> BOARD=<board> json     # resolved state (group 3)
```

The `info-*` outputs are those of `make <target>`. `VAR=VALUE` arguments
are command line variables as for Make (they win over every assignment in
the data). Messages (Make's `$(info …)`) go to stderr. Exit status: 0; 1
usage; 2 an error of the configuration (Make's `$(error …)`, e.g. missing
features); 3 the request is outside the data (a file is not converted).

API (`import resolver`): `resolve(app_dir, {"BOARD": …}) -> dict`,
`boards_supported(app_dir, boards) -> list`, `info(state, target) -> lines`.
Requirements: Python 3, PyYAML.

| File | Purpose |
|---|---|
| `variables.py` | variables of the data (flavors, command line), selections, `%` patterns |
| `evaluate.py` | evaluation of rule lists; includes -> YAML, hooks, Make-only files, out-of-scope errors |
| `pipeline.py` | the algorithm of Make's pipeline files (table below) |
| `resolver.py` | API, command line, JSON state |
| `tests/` | unit, parity and no-Make tests, golden file of `info-boards-supported` |

Data model: what became data, what is algorithm
-----------------------------------------------

Everything that is configuration is YAML in the format of step G0-1
(`dist/tools/config_data/README.md`); the Make file next to it is
generated. Step G0-2 adds:

| Data (source) | Generated for Make | What it holds |
|---|---|---|
| `examples/…/riot-app.yaml` (3 applications) | the application `Makefile` | application configuration: `APPLICATION`, `BOARD ?=`, `RIOTBASE ?= ${CURDIR}/…`, `USEMODULE`, `DEVELHELP`, the `USE_ZEP` condition, `BIN_USEMODULE`, …, and the `include` of `${RIOTBASE}/Makefile.include` |
| `makefiles/defaultmodules_regular.inc.yaml` | `defaultmodules_regular.inc.mk` | default modules, includes of `Makefile.default` of board and CPU (data name `default.yaml`) |
| `makefiles/defaultmodules_no_recursive_deps.inc.yaml` | `….inc.mk` | default modules without dependencies |
| `makefiles/defaultmodules_deps.inc.yaml` | `….inc.mk` | dependencies of default modules |
| `makefiles/stdio.inc.yaml` | `stdio.inc.mk` | stdio backends and their choices (was Make logic, G0-1 limit) |
| `makefiles/features_modules.inc.yaml` | `features_modules.inc.mk` | features -> modules, periph init modules, ignore list |
| `makefiles/deprecated_modules.inc.yaml` | `deprecated_modules.inc.mk` | deprecated modules |
| (existing) `features.yaml` | `features_existing.inc.mk` | all features (`FEATURES_EXISTING`) |
| (G0-1) `deps.yaml`, `provides.yaml` | `Makefile.dep`, `Makefile.features` | dependency rules; provided features and **board/CPU data** (`CPU`, `CPU_MODEL` in the board files, `CPU_CORE`, `CPU_FAM` in `cpu/nrf52`, `CPU_ARCH` in `cpu/cortexm_common`; native64 sets only `CPU`, like Make) |

Decisions:

- **riot-app.yaml is a rule list** of the same format (not a second format
  with fixed keys): one validator, one generator, one evaluator; the
  application needs conditions (`USE_ZEP`) and references
  (`${APPLICATION_MODULE}`) anyway. The whole application `Makefile` is
  generated, so `MAKEFILE_LIST` stays identical (an included adapter file
  would add an entry). `CURDIR` is predefined (the application directory).
- **Schema 2** (`dist/tools/config_data`): the pipeline files need three
  constructs schema 1 does not have; they are added minimally and every
  schema-1 file stays valid and keeps `schema: 1`:
  `{select: {var, match?, except?, replace?: {from, to}}}` as an `add` item
  or `set` value (`$(filter …)`, `$(filter-out …)`, `$(subst …)` of one
  variable), `${NAME}` as a whole pattern word (`$(filter $(LIST),$(V))`)
  and the condition `several` (more than one distinct word selected; Make:
  `_is_greater` of `utils/strings.mk`, which the generator includes, as the
  original `stdio.inc.mk` did). Translator, generator, validator and normal
  form support them; the round trip (original at the base commit =
  generated = YAML) holds for all 53 converted files.
- **Algorithm, not data**: the order of evaluation, the fixpoint, the
  features check, the checks of the result and board filtering are code of
  the build system. They are implemented in `pipeline.py`:

| Algorithm (pipeline.py) | Replaces (Make file:line, base 827338cf72) |
|---|---|
| `prelude` | `Makefile.include:27-38` directories, `:53` Makefile.local, `:74-75` board aliases (rejected), `:128-129` OS, `:153-171` TOOLCHAIN, `:173` (`cargo-settings.inc.mk:49-59`, rejected), `:193-202` BOARDDIR |
| `application` | `Makefile.include:333` Makefile.features, `:343` default modules, `:349` features check, `:352-355`, `:358` dependency resolution, `:496` APPLICATION_MODULE, `:532` + `bindist.inc.mk:2` BIN_USEMODULE |
| `features_check` | `makefiles/features_check.inc.mk:1-93` (also the hook for its `include` in `sys/ztimer/deps.yaml`) |
| `dependency_pass`, `resolve_dependencies` | `makefiles/dependency_resolution.inc.mk:5-40` (one pass, fixpoint over USEMODULE, USEPKG, FEATURES_USED), `:42-95` finalisation, `:97-140` insecure-module checks (not for info goals) |
| `expected_errors` | `Makefile.include:908-993` (DISABLE_MODULE, missing/blacklisted/conflicting features, BOARDS_SUPPORTED/UNSUPPORTED, CONTINUE_ON_EXPECTED_ERRORS) |
| `candidate_boards`, `board_supported` | `makefiles/info-global.inc.mk:14-15`, `:26-74` (info-boards-supported) |
| `features_existing` | reads `features.yaml` (source of `features_existing.inc.mk`) |

How the evaluation keeps Make's semantics: the generated Make files use
`=`, `:=`, `?=`, `+=` for `set`/`add`, so the resolver models the same
flavors (`variables.py`): a recursive variable keeps its references and
selections and evaluates them when used (e.g. `FEATURES_REQUIRED +=
$(filter-out $(PERIPH_IGNORE_MODULES),$(filter periph_%,$(USEMODULE)))`
follows USEMODULE in later passes), a simple one is evaluated once.

What is not data and not read: `include ${RIOTMAKE}/default-radio-settings.inc.mk`
(gnrc_networking) only adds CFLAGS (group 3) and is skipped (`MAKE_ONLY`,
listed in the state; a test checks that it assigns no resolved variable).
To tell "not converted" from "optional and missing", the resolver tests
whether a Make file exists (`os.path.exists`, also `pkg/<name>/Makefile`
for `PKG_PATHS` like Make's `$(wildcard)`); it never opens one.

Scope
-----

`examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on `nrf52840dk` and `native64`
(`dist/tools/config_data/scope.yaml`: 44 dependency/feature files, 6
pipeline files, 3 applications). Requests outside the data stop with exit
status 3 and name the file: another application without `riot-app.yaml`,
another board or module whose `Makefile.dep`/`Makefile.features` is not
converted, a board alias (`native`), `Makefile.local`, Kconfig files
(`app.config`, `user.config`), `RIOT_MAKEFILES_GLOBAL_PRE`,
`APPLICATION_RUST_MODULE`.

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/resolver/tests -v
dist/tools/migration/run_tests.py --step g0-02-resolver
python3 -m unittest discover -s dist/tools/config_data/tests -v   # schema 2, adapters, live Make parity
```

| Rule | Test classes | How |
|---|---|---|
| V1 variables like the generated Make | `test_variables.PatternTest`, `FlavorTest`, `SelectTest` | `%` patterns (positive/negative), flavors, command line, references kept by `add`, lazy selections |
| E1 conditions and rules | `test_evaluate.ConditionTest`, `RuleTest` | each condition true and false; elif/else; order; messages |
| E2 includes | `test_evaluate.IncludeTest` | YAML next to the Make file, `for_each`+`sort`, optional, out of scope, invalid YAML, hooks, Make-only |
| A1 features check | `test_algorithm.FeaturesCheckTest` | arch/bug/cpu, missing, optional, conflicts, one-out-of order, blacklist |
| A2 fixpoint | `test_algorithm.FixpointTest` | chains of 0-3 links = 1-4 passes, feature in a later pass, FEATURES_USED alone triggers a pass, no fixpoint, PKG_PATHS |
| A3 default modules, finalisation | `test_algorithm.DefaultModulesTest` | DISABLE_MODULE, auto_init/periph_init, deprecated, non-existing features, bin modules after resolution |
| A4 order | `test_algorithm.OrderTest` | sorted, without duplicates |
| A5 checks, board filter | `test_algorithm.ExpectedErrorsTest`, `BoardFilterTest`, `MakeOnlyFilesTest` | each problem, CONTINUE_ON_EXPECTED_ERRORS, insecure modules, candidates, missing/conflicting features |
| P1 parity with Make | `test_info_parity.InfoParityTest` | 6 pairs x 10 outputs (info-modules, -packages, -features-used/-missing/-provided, info-cpu, CPU_MODEL/CORE/FAM/ARCH) vs. golden files |
| P2 same work | `test_info_parity.SameWorkTest` | passes = includes of `dependency_resolution.inc.mk` in MAKEFILE_LIST; YAML read = data of the files Make read |
| P3 board filter | `test_info_parity.BoardsSupportedTest` | info-boards-supported (API and CLI) vs. golden |
| P4 command line | `test_info_parity.CommandLineTest` | all targets of a pair, json, exit codes 1/2/3 |
| N1-N3 no Make | `test_no_make.*` | audit-hook trace over the whole sample and three requests outside the data: no Make file opened, no process; stub `make` on PATH never called; no process module imported; positive probes for each detector |
| S1-S5 schema 2, adapters | `config_data/tests/test_schema2.*`, `test_adapters.UpToDateTest` | validator, translator, generator, normal form, file names; generated pipeline/app Makefiles up to date |
| M make parity | `config_data/tests/test_parity.LiveMakeParityTest` | live `make info-*` (10 targets, 6 pairs) and `make -n -k` (hello-world) with the generated files vs. golden |
| O1 register | `dist/tools/migration/tests` | step `g0-02-resolver` (G0, `targets: []`, `provides`) |

67 tests in 5 modules (algorithm 29, variables 11, evaluate 10, info
parity 10, no Make 7; about 12 s, no Make run). Together with
`dist/tools/config_data/tests` (79 tests incl. 17 for schema 2 and the live
Make parity, about 9 s) and `dist/tools/migration/tests`.

Mutation probe (each file copied before the change and restored from the
copy; generated Make files regenerated where the data changed):

| Rule | Deliberate defect | Failing tests |
|---|---|---|
| A1 | one-out-of prefers a usable over a used feature | 1 |
| A1 | `cpu_%` not always required | 11 |
| A2 | only one dependency pass | 33 |
| A2 | FEATURES_USED not part of the fixpoint state | 1 (after adding `test_a_change_of_features_used_alone_starts_another_pass`; first run: not detected) |
| A3 | DISABLE_MODULE ignored when default modules are added again | 5 failures, 6 errors |
| A3 | BIN_USEMODULE added before the resolution | 1 |
| A4 | provided features not sorted | 7 |
| A5 | BOARDS_UNSUPPORTED not checked | 1 |
| A5 | board filter ignores BOARDS_UNSUPPORTED | 2 |
| V1 | `add` expands a recursive value at once | 1 (after adding `test_add_to_a_recursive_variable_keeps_the_reference`; first run: not detected) |
| V1 | command line does not win | 1 |
| E1 | `several` evaluated as `has` | 8 |
| E2 | unconverted Make file silently skipped | 3 failures, 1 error |
| N1 | resolver opens an unconverted Make file | 1 (after tracing requests outside the data too; first run: not detected) |
| N2 | resolver runs `make --version` | 2 |
| D1 | `stdio.inc.yaml`: `several` -> `has`, Make file regenerated | resolver 7, config_data 16 (live Make parity) |
| D2 | gnrc_networking `riot-app.yaml` without `ps`, Makefile regenerated | resolver 3, config_data 4 |
| S1 | validator accepts `${X}` inside a pattern word | 1 |
| S2 | translator drops the `except` of a select | 4 |
| S3 | generator writes `several` without `sort` | 4 failures, 1 error |
| O1 | register: G0 step with a target | 2 (`dist/tools/migration/tests`) |

Golden files: those of G0-1 (`dist/tools/config_data/tests/golden/`,
recorded on 827338cf72), extended by `info-cpu` and
`info-debug-variable-CPU_MODEL/CORE/FAM/ARCH`, recorded on the same commit
from `git archive` (`record_golden.py --root … --add …`; the archive gave
the identical output for the targets already recorded); and
`tests/golden/boards-supported.txt` (`tests/record_golden.py`, BOARDS in
the environment). The build command list is compared with RIOT_VERSION
masked (it names the branch of the checkout).

Limits
------

- Only the scope above; each further application/board needs its files
  converted (`config_data.py translate`, `scope.yaml`).
- Not modelled: the toolchain check (`Makefile.include:968-983`, needs
  `TOOLCHAINS_SUPPORTED` of the CPU's `Makefile.include`; both CPUs support
  `gnu`), Kconfig, board aliases, the environment (only command line
  variables; the golden files were recorded with `env -i`), messages of
  deprecated boards/CPUs, colours. `equals` compares values word by word
  (Make compares the text).
- Messages go to stderr (Make prints `$(info …)` on stdout, e.g. the alias
  line of info-boards-supported).
- `several` is `_is_greater(n, 1)` in Make, exact for every count.
