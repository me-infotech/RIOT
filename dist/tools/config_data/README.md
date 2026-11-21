Configuration as data (migration step G0-1)
==========================================

RIOT's dependency rules (`Makefile.dep`) and provided features
(`Makefile.features`) are moved out of Make syntax into YAML. The YAML file
next to each Make file is the **source**; the Make file is **generated**
from it and checked in, only so that GNU Make keeps working until nothing
reads it any more (same pattern as `features.yaml` →
`makefiles/features_existing.inc.mk`). No Make target is migrated in this
step, and Make gives exactly the same results as before.

Next steps: G0-2, a resolver that reads only these YAML files; then the
build without Make (group 3).

| File | Purpose |
|---|---|
| `config_data.py` | command line: `generate [--check]`, `validate`, `translate`, `roundtrip`, `scope` |
| `rules.py` | file names, `${NAME}` references, YAML output, normal form for comparisons |
| `schema.py` | validator of the format (schema 1) |
| `translate.py` | translator Make file → rules (one-off conversion, kept for later scopes) |
| `generate.py` | generator rules → Make file (the adapter) |
| `scope.yaml` | applications and boards of the sample and the files converted for them |
| `tests/` | unit and parity tests, golden files of Make |

```sh
just generate-config-data                                 # regenerate every Make file from its YAML
dist/tools/config_data/config_data.py generate --check    # CI: Make files up to date
dist/tools/config_data/config_data.py validate            # YAML against the schema
dist/tools/config_data/config_data.py translate <Makefile.dep>…   # convert (writes the YAML)
dist/tools/config_data/config_data.py roundtrip           # original = generated = YAML
dist/tools/config_data/config_data.py scope --check       # scope.yaml = files Make reads
```

Edit the YAML, never the generated Make file. Requirements: Python 3 and
PyYAML; `generate`, `validate` and `translate` need neither Make nor git.

File names
----------

| Make file (generated) | YAML (source) |
|---|---|
| `Makefile.dep` | `deps.yaml` |
| `Makefile.<x>.dep` | `<x>.deps.yaml` |
| `Makefile.features` | `provides.yaml` |
| `Makefile.<x>.features` | `<x>.provides.yaml` |

(`features.yaml` is taken: it lists all features of RIOT.)

Format (schema 1)
-----------------

Schema 2 (step G0-2) and schema 3 (step G3-1: `files`, `subdirs`, `arith`
values; `pattern`, `macro`, `unique` in a selection; conditions `at_least`,
`nonempty`; module data `module.yaml` -> generated module `Makefile`) are
described in `dist/tools/resolver/README.md` and
`dist/tools/cmake_gen/README.md`.

```yaml
schema: 1
rules:                       # evaluated in order, like the Make file
  - comment: why             # optional on every rule; alone it is a standalone comment
    if: {has: {var: USEMODULE, match: [gnrc_%], except: [gnrc_netif%]}}
    then:
      - add: {USEMODULE: [gnrc]}
    elif:                    # optional: further branches (`else ifeq`)
      - if: {equals: {OS: Linux}}
        then: [...]
    else: [...]              # optional
```

Every condition and action is structured. The only reference to another
value is `${NAME}` (the value of variable NAME) inside a text; no Make
function and no other Make syntax is accepted (`schema.py`).

| Condition | True when | Make (generated) |
|---|---|---|
| `has: {var, match, except?}` | a word of `var` matches a pattern of `match` and none of `except` | `ifneq (,$(filter M,$(filter-out E,$(V))))` |
| `selection_equals: {var, match, except?, words}` | the words of `var` selected like `has`, in order and with repetitions, are exactly `words` | `ifeq (W,$(filter M,$(V)))` |
| `one_of: {var, values}` | the value of `var` is one of `values` | `ifneq (,$(filter $(V),A B))` |
| `equals: {VAR: value, …}` | each variable has exactly this value (`''`: empty); with several variables each value is one word | `ifeq ($(A) $(B),a b)` |
| `not: <condition>` | the condition is false | `ifeq` ↔ `ifneq` |

Patterns are words with at most one `%` (Make's pattern rule).

| Action | Meaning | Make (generated) |
|---|---|---|
| `add: {VAR: [items]}` | append the items | one `VAR += item` per item |
| `set: {var, value, flavor?}` | assign; `flavor`: `recursive` (default), `simple` (value expanded now), `conditional` (only if unset) | `=`, `:=`, `?=` |
| `include: {path, optional?}` | read the rules of another file | `include` / `-include` |
| `include: {for_each, path, sort?, optional?}` | include `path` with `%` replaced by each word of `for_each`; `sort`: sorted, without duplicates | `-include $(sort $(V:%=…%…))` |
| `error` / `warning` / `info: text` | stop with / print the message | `$(error …)` … |

An `include` names the Make file of the other directory (the resolver of
G0-2 reads the YAML next to it; a file not yet converted is still Make).

### Former Make expressions and their structured form

The earlier exploratory format (D27, test log 2026-11-14) kept 10 rules
as raw Make expressions (`make_expr`). All of them, and the new cases of
the `Makefile.features` files, are now structured:

| File | Make | Structured form | Why it is the same |
|---|---|---|---|
| `Makefile.dep` | `-include $(EXTERNAL_MODULE_PATHS:%=%Makefile.dep)` | `include: {for_each: EXTERNAL_MODULE_PATHS, path: '%Makefile.dep', optional: true}` | substitution reference = one path per word |
| `Makefile.dep` | `-include $(PKG_PATHS:%=%Makefile.dep)` | `include: {for_each: PKG_PATHS, …}` | as above |
| `Makefile.dep` | `-include $(sort $(USEMODULE:%=$(RIOTBASE)/drivers/%/Makefile.dep))` | `include: {for_each: USEMODULE, path: '${RIOTBASE}/drivers/%/Makefile.dep', sort: true, optional: true}` | `sort` is a flag of the include |
| `Makefile.dep` | same for `sys/%` | same with `sys/%` | as above |
| `drivers/Makefile.dep` | `$(filter at86rf%, $(filter-out at86rf215%, $(USEMODULE)))` | `has: {var: USEMODULE, match: [at86rf%], except: [at86rf215%]}` | filter and filter-out keep or drop each word by itself |
| `drivers/Makefile.dep` | `$(filter-out netdev_default …, $(filter netdev_%,$(USEMODULE)))` | `has: {…, match: [netdev_%], except: [netdev_default, …]}` | same set of words in either order of the two functions |
| `sys/net/gnrc/Makefile.dep` | `$(filter gnrc_%,$(filter-out gnrc_lorawan …,$(USEMODULE)))` | `has: {…, match: [gnrc_%], except: [gnrc_lorawan, …]}` | as above |
| `sys/net/gnrc/Makefile.dep` | `$(filter gnrc_netif_%,$(filter-out gnrc_netif_pktq,$(USEMODULE)))` | `has: {…, match: [gnrc_netif_%], except: [gnrc_netif_pktq]}` | as above |
| `sys/net/gnrc/Makefile.dep` | `ifeq (shell_cmd_gnrc_pktbuf,$(filter gnrc_pktbuf_%, $(USEMODULE)))` | `selection_equals: {var: USEMODULE, match: [gnrc_pktbuf_%], words: [shell_cmd_gnrc_pktbuf]}` | compares the selection with literal words; this rule can never be true (the word does not match the pattern) and is kept as it is |
| `sys/shell/Makefile.dep` | `ifeq (periph_rtt,$(filter periph_rtc periph_rtt,$(USEMODULE)))` | `selection_equals: {…, match: [periph_rtc, periph_rtt], words: [periph_rtt]}` | "periph_rtt used, periph_rtc not" |
| `cpu/cortexm_common/Makefile.features` | `ifneq (,$(filter $(CPU_CORE),cortex-m33 cortex-m4f cortex-m7))` | `one_of: {var: CPU_CORE, values: [...]}` | the variable is the pattern, the list the words |
| `cpu/native/Makefile.features` | `ifeq ($(OS) $(OS_ARCH),Linux x86_64)` | `equals: {OS: Linux, OS_ARCH: x86_64}` | with one-word values, `"$(OS) $(OS_ARCH)"` equals `"Linux x86_64"` exactly when both are equal |
| `cpu/cortexm_common/Makefile.features` | `else ifeq …` chain | `elif:` list | one `endif` closes all branches |
| `Makefile.features` | `FEATURES_PROVIDED += cpu_$(CPU)`, `$(error $(BOARD): …)` | `cpu_${CPU}`, `error: '${BOARD}: …'` | plain variable reference |
| `cpu/native/Makefile.features` | `DISABLE_LIBSTDCPP ?= 1`, `CPU_ARCH := armv6m` | `set` with `flavor: conditional` / `simple` | Make's three assignment flavors |

Scope
-----

Exactly the dependency and feature files Make reads for the sample:
`examples/basic/hello-world`, `examples/networking/gnrc/networking`
(gnrc_networking) and `examples/advanced/bindist` on `nrf52840dk` and
`native64`. Determined on the base commit `827338cf72` with
`make -C <app> BOARD=<board> info-debug-variable-MAKEFILE_LIST` (union over
the six pairs, every file named `Makefile*.dep` or `Makefile*.features`);
`config_data.py scope --check` and the tests repeat it.

| | Count |
|---|---|
| files converted | **44** (33 `Makefile*.dep`, 11 `Makefile.features`) |
| such files in the repository | 1157 (756 `Makefile*.dep`, 401 `Makefile*.features`) |
| rules in the 44 files | 1402 (621 conditions, 695 `add`, 21 `set`, 61 `include`, 4 messages) |
| rules kept as Make expressions | **0** |

The other 1113 files are converted later with `config_data.py translate`
(adding applications and boards to `scope.yaml`). Constructs not seen in
the 44 files (`ifdef`, `define`, `export`, `$(shell …)`, `$(foreach …)`,
…) are rejected by the translator with file and line; the format is
extended for them when a scope needs them.

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/config_data/tests -v
dist/tools/migration/run_tests.py --step g0-01-config-data
```

CI runs them in the `migration-tests` workflow (step `g0-01-config-data`
in `dist/tools/migration/steps.yaml`).

| Rule | Test classes | How |
|---|---|---|
| C1 data is valid and structured | `test_schema.ValidDocumentTest`, `InvalidDocumentTest` | sample with every construct; all repository YAML; 39 negative samples (Make syntax, wrong types, missing keys) |
| C2 translator | `test_translate.ConditionTest`, `StatementTest`, `StructureTest` | each construct in both argument orders; 23 unsupported samples fail with file:line |
| C3 generator | `test_generate.ConditionTextTest`, `RuleTextTest` | exact Make text for each condition (and its negation), action, branch, layout and header |
| C4 round trip | `test_roundtrip.RoundTripTest`, `RepositoryRoundTripTest` | rules of original (git, base commit) = generated = YAML for the 44 files; fixpoint; a changed rule is found (skipped without the base commit) |
| C5 adapters up to date | `test_adapters.UpToDateTest`, `CheckDetectsStaleFilesTest`, `JustRecipeTest` | `generate --check`; stale YAML, hand-edited or missing Make file and invalid YAML on a copy; `just --dry-run generate-config-data` |
| C6 Make parity | `test_parity.LiveMakeParityTest` | live `make info-modules/-packages/-features-used/-features-missing/-features-provided/-debug-variable-MAKEFILE_LIST` for 6 pairs and `make -n -k` for hello-world vs. golden files of the base commit |
| C7 scope | `test_parity.GoldenFilesTest`, `LiveScopeTest`, `test_adapters.UpToDateTest` | MAKEFILE_LIST of the goldens and of a live run = `scope.yaml`; YAML files = scope |
| C8 no Make | `test_adapters.NoMakeTest` | data modules start no process; `generate --check`/`validate` with no `make` on `PATH` |

62 tests in 6 modules (translate 24, adapters 14, parity 7, round trip 7,
generate 5, schema 5; about 6.5 s, Make runs one at a time). Without GNU
Make the live parity and scope tests are skipped, without the base commit
the repository round trip, without just the recipe test.

Mutation probe (each file copied before the change and restored from the
copy afterwards; every defect makes tests fail):

| Rule | Deliberate defect | Failing tests |
|---|---|---|
| C2 | translator swaps the meaning of `ifeq`/`ifneq` | 48 failures, 2 errors |
| C2 | translator drops the `except` of a `filter-out` | 4 (incl. repository round trip) |
| C3 | generator writes `one_of` negated | 5 (incl. up-to-date check) |
| C3 | generator drops `sort` of a `for_each` include | 5 |
| C1 | validator accepts `$` (Make syntax) in text | 3 failures, 1 error |
| C1 | validator accepts `not` inside `not` | 1 |
| C4 | normal form ignores `else` branches | 3 |
| C5 | `generate --check` never reports a stale file | 3 |
| C5 | just recipe runs `generate --check` instead of `generate` | 1 |
| C6 | `provides.yaml`: `cpu_${CPU}` changed, Make file regenerated | 40 failures, 1 error (live parity) |
| C6 | `cpu/native/deps.yaml`: `fdcan` changed, Make file regenerated | 6 (live parity, round trip) |
| C7 | one file left out of `scope.yaml` | 3 |
| C8 | `generate.py` imports `subprocess` | 1 |
| O1 | register accepts a `G0` step with targets | 1 (`dist/tools/migration/tests`) |

The first probe found a gap: a normal form that ignored `else` went
unnoticed, because both sides of every comparison lost the same branch.
`RoundTripTest.test_a_changed_else_or_elif_branch_is_found` closes it.

Golden files (`tests/golden/`, `tests/record_golden.py`): recorded on
`827338cf72` with GNU Make 4.3, `env -i PATH HOME LC_ALL=C`; header with
command, commit, date, Make and compiler versions. The `make -n -k` list
holds host compiler flags and is compared only on a host with the
compilers of the header (skipped otherwise, e.g. in CI).

Parity result (2026-11-20): 36/36 info outputs and 2/2 build command lists
identical; 44/44 round trips; the 24 info outputs that also exist in the
golden files of the earlier resolver attempt (`fd870b43a9`, same content of
these files) are identical to them. Beyond the sample (mixed operation),
one run against all info goldens of that attempt (hello-world,
gnrc_networking, tests/periph/rtc on ten boards of nine CPU families,
including error exits): 210/210 identical.

Extension of step G0-2 (schema 2, pipeline rules, applications)
---------------------------------------------------------------

Step G0-2 (`dist/tools/resolver`) needs no Make file at all, so the rule
files of the build system pipeline and the application Makefiles became
data too (`scope.yaml`: `pipeline`, `applications`):

| Make file (generated) | YAML (source) |
|---|---|
| `makefiles/<name>.inc.mk` | `makefiles/<name>.inc.yaml` (6: default modules x3, `stdio`, `features_modules`, `deprecated_modules`) |
| application `Makefile` | `riot-app.yaml` (3 applications) |
| `Makefile.default` | `default.yaml` (name only; none in the scope) |

Schema 2 adds, for those files only (a file declares the lowest schema it
needs; the 44 files keep `schema: 1`):

| Construct | Meaning | Make (generated) |
|---|---|---|
| `{select: {var, match?, except?, replace?: {from, to}}}` as `add` item or `set` value | the words of `var` that match and are not excepted, `from` replaced by `to` | `$(subst F,T,$(filter M,$(filter-out E,$(V))))` |
| `${NAME}` as a whole pattern word | the words of NAME are the patterns | `$(filter $(NAME),…)` |
| `several: {var, match, except?}` | more than one distinct word selected | `ifeq (1,$(call _is_greater,$(words $(sort …)),1))`, with `include $(RIOTMAKE)/utils/strings.mk` first in the file |

Round trip: 53/53 files (44 + 6 + 3) original = generated = YAML. The
golden files gained `info-cpu` and `info-debug-variable-CPU_MODEL/CORE/FAM/ARCH`
(same base commit, `record_golden.py --add`); the build command list is
compared with RIOT_VERSION masked. Tests: `test_schema2.py` (S1-S5, 17
tests); the whole directory now has 79 tests.

Limits
------

- Only 44 of 1157 files; Make reads converted and unconverted files mixed.
- Two `include`s pointed to Make logic, not data: `makefiles/stdio.inc.mk`
  (from `sys/Makefile.dep`; data since G0-2) and
  `makefiles/features_check.inc.mk` (from `sys/ztimer/Makefile.dep`; an
  algorithm, implemented by the resolver of G0-2).
- Comments are kept, the layout of the generated files is not (blank
  lines, alignment, trailing comments move above their line).
- Board and CPU build data (`Makefile.include`) is not part of this step.

Step G0-3: the build data is the only source of the build flags
----------------------------------------------------------------

Step G3-1 wrote the build data (`build.yaml`, `<x>.build.yaml`, `pkg.yaml`,
`<x>.pkg.yaml`, see `dist/tools/cmake_gen/README.md`) next to the board,
CPU, build system and package Make files and left those Make files
unchanged: a second source, kept equal by parity tests. Step G0-3 removes
it. The Make files no longer hold the build part; it is generated from the
data by `just generate-config-data` (`config_data.py generate`), like the
module Makefiles and the dependency files. Make reads the generated files,
the build without Make (`just build`) reads the data: one source.

`scope.yaml` `build` names, for each of the 35 data files, the Make file it
describes and its adapter:

| Adapter | Files | Generated | The Make file |
|---|---|---|---|
| `whole` | 19 (e.g. `sys/build.yaml`, `makefiles/cflags.build.yaml`, `makefiles/pseudomodules.build.yaml`, `makefiles/vars.build.yaml`) | the Make file itself | - |
| `part` | 15 (e.g. `build.yaml`, `cpu/nrf52/build.yaml`, `pkg/pkg.build.yaml`, `pkg/cmsis/pkg.yaml`) | `<data name>.mk` next to the data (`build.yaml` -> `build.mk`, `nrfx.pkg.yaml` -> `nrfx.pkg.mk`) | keeps what is not data (flashing, debugging, terminal, Docker, Kconfig, riotboot, the rules of the build and of the packages) and includes the generated file where the build part was |
| `none` | 1 (`sys/event/build.yaml`) | nothing: every rule is a `stand_in` | unchanged |

A build part that is not contiguous in its Make file is split into
sections (`- section: <name>`; `build.yaml` 8, `pkg/pkg.build.yaml` 3,
`makefiles/libc/newlib.build.yaml` 2). The generated file has one block per
section; the Make file includes it once per section:

```make
RIOT_BUILD_SECTION := toolchain
include $(RIOTBASE)/build.mk
```

Each block clears `RIOT_BUILD_SECTION` (so the sections of a generated file
included inside it are not mistaken for its own); a name without a block
stops Make. Where the Make file had other statements between data lines
that do not depend on them, those statements were moved before or after
the generated part instead (e.g. `cpu/nrf52/Makefile.include`,
`makefiles/toolchain/gnu.inc.mk`, the IoT-LAB and unzip settings of
`Makefile.include`); the order of everything that reads or changes a build
variable is unchanged.

Build data and flash data (step G3-2, `dist/tools/flash/README.md`) do not
share a value. The programmer settings are flash data; a Make file with
both includes its flash adapter (`flash.inc.mk`, `<x>.flash.inc.mk`) as
its first statement and its build part where the build part was. Where the
Make file is generated whole (`makefiles/vars.inc.mk`), the build data
holds that include as its first rule; the build without Make skips the
include of a flash adapter (`cmake_gen/buildeval.py`), the flash without
Make reads the flash data. Two values are read by both: FLASH_ADDR (default
`0x0`, exported to the modules) and FLASHFILE (in BUILD_FILES). Their only
source is the flash data (`makefiles/vars.flash.yaml`,
`makefiles/tools/<programmer>.flash.yaml`); the build without Make does not
read flash data, so both are empty there (FLASHFILE is ELFFILE, which
BUILD_FILES names anyway; no module reads FLASH_ADDR), while Make reads them
through the adapters, so its values are unchanged.

Schema 4 adds what the generated Make needs to say exactly what the Make
file said (every schema 1-3 file stays valid):

| Construct | Meaning | Make (generated) |
|---|---|---|
| `- section: NAME` | the following rules form a section (top level; all or no rules of a file) | `ifeq (NAME,$(RIOT_BUILD_SECTION))` block |
| `stand_in: <Make file>` on any rule | read by the build without Make only: it stands for what that Make file still does itself (a recipe, Kconfig, git-cache-rs, …) | left out |
| `export: [NAMES]`, `unexport: [NAMES]`, `set: {…, export: true}` | exported to the Make processes of modules and packages (the build without Make collects them in BUILD_EXPORTED) | `export X`, `unexport X`, `export X = …` |
| value `{when: {test: SEL, then?, else?}}` | `then` if the selection is not empty, else `else`; evaluated when the variable is used | `$(if SEL,THEN,ELSE)` |
| `files: {…, sort: true}` | sorted, without duplicates | `$(sort $(wildcard …))` |
| `arith: {…, once: true}` | expanded once (only as the value of a `set`) | `$(call memoized,VAR,$(shell …))` |
| `arith: {…, kilo: [VAR…]}` | only these variables may hold `NK`; another one with `NK` is an error (in Make the shell gets no number) | `$(VAR:%K=%*1024)` for those, `$(V)` for the others |
| a `set` value that ends with blanks (with a one-line `comment`) | the blanks are part of the value | `VAR = value  # comment` (Make keeps the blanks before a comment) |
| condition `defined: VAR` | the variable has a non-empty value, not expanded | `ifdef VAR` / `ifndef VAR` |
| condition `count: {var, match?, except?, is: N}` | the selection has N words (repetitions count) | `ifeq (N,$(words SEL))` |

The schema 3 constructs that were "build data only" are written as Make
now: `arith` as `$(shell echo $$((…)))` or `printf "0x%x"` with
`$(V:%K=%*1024)`, `unique` as `$(strip $(call uniq,…))` of `Makefile.include`
(applied to the selected words before `replace`, `macro` and `pattern`, as
Make did). `cpu/cortexm_common/build.yaml` reads ROM_OFFSET and FW_ROM_LEN
with `when`, so the build without Make evaluates them lazily too.

Doxygen: comment lines that start with `#` are written as `##` lines. The
documentation of `makefiles/pseudomodules.inc.mk` (an input of
`doc/doxygen/riot.doxyfile` and of `dist/tools/doccheck`) and of
`drivers/netdev_ieee802154_submac/Makefile.include` is kept in the data, as
the comments of the rules it documents, and generated with the Make file.
Choice: the documentation stays next to the pseudomodule it documents, in
the one file a developer edits; a separate documentation file would be a
second list of the pseudomodules. The `##` lines are the originals, in the
same order (B6); only blank lines between entries moved.

Probes and values of the build algorithm: the data reads the answers of
the toolchain and git as PROBE_* and two values of the algorithm as
BUILD_RIOT_VERSION_TUPLE and BUILD_EXTDEFINES (dist/tools/cmake_gen computes
them in Python). For Make, `makefiles/build_providers.inc.mk` defines them
with the commands the Make files used before (recursive; memoized where the
original was simple or memoized). It is the algorithm, not data, and goes
away with Make.

### Rules and tests

```sh
python3 -m unittest discover -s dist/tools/config_data/build_tests -v
dist/tools/migration/run_tests.py --step g0-03-build-flags-data
```

47 tests in 4 modules (about 7 s; Make runs one at a time).

| Rule | Test classes | How |
|---|---|---|
| B1 schema 4 validator | `test_schema4.ValidatorTest` | 14 positive, 17 negative samples; schema 4 needed |
| B2 generator | `test_schema4.GeneratorTest` | exact Make text of each construct, sections, stand-ins left out, `##` lines |
| B3 evaluator | `test_schema4.EvaluatorTest` | `when` lazy, `defined` unexpanded, `count` with repetitions, export/unexport, sorted files, unique before the pattern, stand-in and section rules read |
| B4 register | `test_adapters.RegisterTest` | all 35 data files in scope.yaml `build`, Make file next to the data, `none` = only stand-ins |
| B5 one source | `test_adapters.OneSourceTest` | `generate --check`; header; a split Make file includes its part once per section and holds none of its lines; stand-ins name Make files that are not generated; every probe defined once for Make and known to the build without Make |
| B6 round trip | `test_adapters.RoundTripTest` | original (scope.yaml `build_base`) = generated = data for the 10 files written by the translator; Doxygen lines unchanged; a changed rule is found (skipped without the base commit) |
| B7 Make parity | `test_make_parity.*` | live Make: value of every variable the data writes (173) and the exported environment (98) for the three applications on nrf52840dk = golden files of the base commit (`record_golden.py`); detector sample |
| B8 stale | `test_adapters.StaleTest` | changed data, edited or missing generated file are found (on a copy) |
| B9 exact values | `test_exact_values.*` | Make with the original text = Make with the generated file = build without Make: the branch suffix of the version (8 branch names, also names ending in `master`), SLOT_AUX_OFFSET (`NK` in ROM_LEN only; 4 accepted, 2 refused forms), PKG_VERSION of pkg/cmsis with its two trailing blanks |

The second-source checks of step G3-1 became adapter checks:
`cmake_gen/tests/test_schema3.DataFilesTest` (each data file is registered
with its Make file), `NamesTest` (build data is no adapter source by name;
the register names it), `GeneratorTest` (`arith` and `unique` are written as
Make). The G0 parity tests (`tests/test_parity.py`) mask what the split
changes by construction (`sample.mask_g003`): the generated files in
MAKEFILE_LIST and line numbers in Make's messages about the split files.

Mutation probe (each file copied before the change and restored from the
copy; the generated files regenerated from the restored data):

| Part | Deliberate defect | Failing tests |
|---|---|---|
| B1 | validator accepts any section name (`dist/tools/config_data/schema.py`) | g003: 1 |
| B2a | sections do not clear RIOT_BUILD_SECTION (`dist/tools/config_data/generate.py`) | g003: 3, config_data: 2 |
| B2b | stand-in rules written as Make (`dist/tools/config_data/generate.py`) | g003: 7 |
| B2c | `when`: then and else swapped (`dist/tools/config_data/generate.py`) | g003: 4 |
| B2d | `defined` written as a test of the expanded value (`dist/tools/config_data/generate.py`) | g003: 3 |
| B2e | Doxygen lines written as `# #` (`dist/tools/config_data/generate.py`) | g003: 2 |
| B3a | evaluator: `when` takes the other branch (`dist/tools/resolver/variables.py`) | g003: 1, cmake_gen: 8 |
| B3b | evaluator: export ignored (`dist/tools/resolver/evaluate.py`) | g003: 1, cmake_gen: 14 |
| B3c | evaluator: `count` without repetitions (`dist/tools/resolver/evaluate.py`) | g003: 1 |
| B4 | register: cpu/nrf52 marked whole (`dist/tools/config_data/scope.yaml`) | g003: 2 |
| B5a | generate/check skip the build data (`dist/tools/config_data/config_data.py`) | g003: 1 |
| B5b | Make file keeps a line of its generated part (second source) (`boards/common/nrf52/Makefile.include`) | g003: 4, cmake_gen: 3 |
| B5c | Make file no longer includes the toolchain section (`Makefile.include`) | g003: 4, config_data: 38, cmake_gen: 3 |
| B5d | generated file edited by hand (`cpu/nrf52/build.mk`) | g003: 6, cmake_gen: 3 |
| B5e | probe: -std=c11 always supported (Make) (`makefiles/build_providers.inc.mk`) | g003: 3, config_data: 1, cmake_gen: 3 |
| B6 | pseudomodules data: one Doxygen line changed (`makefiles/pseudomodules.build.yaml`) | g003: 1 |
| B7a | data: cortexm -Os -> -O2 (`makefiles/arch/cortexm.build.yaml`) | g003: 3, config_data: 1, cmake_gen: 10 |
| B7b | data: export of GENSRC dropped (`build.yaml`) | g003: 6 |
| B7c | data: ROM_OFFSET symbol added always (`cpu/cortexm_common/build.yaml`) | g003: 3, cmake_gen: 10 |
| B9a | value with trailing blanks written without them (`dist/tools/config_data/generate.py`) | g003: 1, config_data: 2 |
| B9b | data: branch suffix cuts a leading `master` (`makefiles/git_version.build.yaml`) | g003: 4 |
| B9c | evaluator: `NK` accepted in every variable (`dist/tools/resolver/variables.py`) | g003: 3 |
| B9d | generator: `kilo` ignored (`dist/tools/config_data/generate.py`) | g003: 2 |
| B9e | data: slot_aux without `kilo` (`sys/slot_aux/build.yaml`) | g003: 3 |
| B9f | data: cmsis PKG_VERSION without the two blanks (`pkg/cmsis/pkg.yaml`) | g003: 1, config_data: 1 |

25/25 defects detected (2026-11-21; git status and the checksums of every changed file are the same before and after).

### Parity (2026-11-21)

* G0 goldens (`tests/`): 36/36 info outputs and 2/2 `make -n -k` lists
  identical (after `mask_g003`; the commands byte for byte).
* G3-1 goldens (`dist/tools/cmake_gen/tests`, P1-P4): the build without Make
  still gives Make's commands (44, 153, 45 objects, link, objcopy, size,
  headers), and live Make with the generated files gives the commands of
  the base commit.
* B7: 173 variables and 98 exported variables x 3 applications identical.
* Beyond the scope (one-off, base commit vs. now: `make -p` with every
  variable expanded and the environment of a recipe, 17 boards (nRF52/53, SAM, STM32,
  Kinetis, RP2350, ESP32, AVR, RISC-V, LPC23xx, native) x 3 applications, 7 variants on nrf52840dk - DEVELHELP=0,
  WERROR=0 LOG_LEVEL=4, LTO=1, RIOT_CI_BUILD=1, TOOLCHAIN=llvm, QUIET=0,
  VERBOSE_ASSERT=1 - and the sub-makes of the 3 packages, 61 runs): every
  expanded value and every exported variable identical, except MAKEFILE_LIST
  and what is computed from it (the prerequisites of the package state
  files: each package is patched again once after the change) and line
  numbers in Make's messages. New variables: the probes and four helpers
  of the data; gone: `_OBJCOPY`, `_OBJDUMP`, `USEMODULE_INCLUDES_`.

### Limits

* Make's text changed where the data says the same with its own
  constructs (`ifeq ($(V),1)` for `ifeq (1,$(V))`, `$(patsubst %,-I%,…)` for
  `$(addprefix -I,…)`, one `+=` per item, comments above instead of after a
  line, blank lines); the values are the same (parity above, B7, B9).
* Values first written in a simpler form are exact again (B9): the branch
  suffix cuts a trailing `master` like `$(GIT_BRANCH:master=)` (helper
  BUILD_GIT_BRANCH_STEM), SLOT_AUX_OFFSET takes `NK` in ROM_LEN only
  (`kilo`; the generated line is the original one), PKG_VERSION of pkg/cmsis
  keeps its two trailing blanks (the generated line is
  `PKG_VERSION = <hash>  # 5.9.0`), so Make's git commands are byte for byte
  those of the base commit (G0 `make -n -k`, compared without masking
  blanks). The build without Make strips the version (`pkg_prepare.py`, as
  in step G3-1) and stops at an `NK` SLOT_AUX_LEN, where Make passes an
  empty offset to the linker.
* New Make files in MAKEFILE_LIST: pkg/pkg.mk makes the state files of a
  package (`.pkg-state.git-downloaded`, `-patched`) depend on MAKEFILE_LIST.
  A package tree prepared before the change (BUILD_DIR/pkg, or the nRF
  vendor headers) is therefore prepared once more on the next build, as
  after any change of a Make file of the package: `git cat-file -e` finds
  the version (no fetch), `git clean`, `git checkout -f <version>`, the same
  patches (`git am` makes new commits in the package's own repository, with
  the same tree), the same headers copied. The sources have the same
  content, so the objects and the firmware are the same; only the package's
  objects are compiled again. A fresh build directory is not affected.
* Only the 35 Make files of the scope; every other board, CPU and package
  Make file is unchanged Make. The stand-ins (15 rules in 9 files) mark
  what the build without Make does not cover yet; the Make file keeps it.
