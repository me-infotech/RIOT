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
