<!--
SPDX-FileCopyrightText: 2026 RIOT contributors
SPDX-License-Identifier: LGPL-2.1-only
-->

# RIOT Build-System Migration

**Status (2026-11-12):** task layer (roadmap P3) implemented in the working
tree of `master` (`0be9299ca9`), **uncommitted**. The 36 group-1 targets are
extracted from Make completely and run with `just`. Groups 2A/2B/2C/3 are
unchanged and stay in Make until the build layer (CMake + Ninja, compared
with Meson + Ninja) takes them over.

## Rule

The migration moves responsibility **out of** Make (decision log D17, D20):

- `just` holds only group-1 targets: no application/board/CPU context, no
  build, no artifact, no runtime state, no artifact lifecycle.
- A just recipe never calls `make`, neither directly nor through a script,
  and reads no Make-resolved state.
- A migrated target has **no entry in any Makefile** (no rule, no forward,
  no `.PHONY`). RIOT's own callers and documentation use `just`.
- All settings of the task layer live in **one file**, `just/settings.just`.

Scope: `.claude/research/just-scope.md`; comparison with the inventory:
`riot-build-config-thesis/docs/05-migration-concept/riot_all_make_targets_neu.xlsx`.

## Layout

| File | Content |
|---|---|
| `justfile` | shell setting and `import` of the files below (35 lines) |
| `just/settings.just` | all constants, defaults and inputs (single source) |
| `just/repository.just` | `[repository]` welcome, print-versions, info-boards, info-emulated-boards, info-applications, list-ttys |
| `just/generate.just` | `[generate]` generate-features, riotgen-installed, generate-{board,driver,example,module,pkg,test} |
| `just/doc.just` | `[doc]` doc, doc-man, doc-latex, doc-starlight, doxygen-*, graphviz-check, starlight-* |

`import` keeps the recipe names unprefixed (`just info-boards`, `just doc`).

## Implemented targets

| Former Make target(s) | just recipe | Removed from |
|---|---|---|
| `welcome`, `print-versions`, `generate-features`, `doc`, `doc-man`, `doc-latex`, `doc-starlight` | same names | `Makefile` |
| `list-ttys`, `doc`, `doc-man`, `doc-latex` (application directories) | same names, run from anywhere | `Makefile.include` |
| `info-boards`, `info-emulated-boards` | same names | `makefiles/boards.inc.mk` (also app context) |
| `info-applications` | same name | `makefiles/app_dirs.inc.mk` |
| `riotgen-installed`, `generate-{board,driver,example,module,pkg,test}` | same names | `makefiles/tools/riotgen.inc.mk` (file deleted) |
| `doc`, `doc-man`, `doc-latex`, `html`, `man`, `latex`, `check` (doc/doxygen) | `doxygen-doc`, `doxygen-doc-man`, `doxygen-doc-latex`, `doxygen-html`, `doxygen-man`, `doxygen-latex`, `doxygen-check` | `doc/doxygen/Makefile` |
| `doxygen-version`, `graphviz-check` | same names | `doc/doxygen/Makefile` |
| `build`, `preview`, `dev`, `integrate_outside_files`, `code_of_conduct`, `governance`, `lostandfound`, `coding_conventions`, `coding_conventions_cpp`, `security`, `unittests`, `contributing` (doc/starlight) | `starlight-<target>` | `doc/starlight/Makefile` |

Still Make targets: `doc-ci` and root `static-test` (decision D18; `doc-ci`
calls `just doxygen-doc`), `docclean`, `pkg-clean`, `clean`, `distclean`,
`info-applications-supported-boards`, starlight `install` (calls
`just starlight-install`; the name is group 2C) and `clean`, the 15 GNU Make
function tests, and every group 2A/2B/2C/3 target. `make` in the base
directory (no goal or an unknown goal) prints a short pointer to
`just --list`.

### Inputs

| Input | How to give it | As in Make |
|---|---|---|
| `APPLICATION_DIRS`, `EMULATED_BOARDS`, `DOCUMENTATION_FORMAT`, `Q` | `just NAME=value <recipe>` (environment ignored) | command line only (`:=`; `Q` is set from `QUIET`) |
| `QUIET` | environment or `just QUIET=0 <recipe>` | environment or command line (`?=`) |
| `BOARDS`, `BOARDSDIRS`, `EXTERNAL_BOARD_DIRS`, `RIOTBOARD`, `RIOTBASE`, `RIOTTOOLS`, `DOXYGEN`, `CC_NOCOLOR` | environment | environment or command line (`?=`) |

Without an application context, `info-boards` and `info-emulated-boards`
use only the inputs given; an `EXTERNAL_BOARD_DIRS` set in an application's
Makefile must be passed explicitly (`EXTERNAL_BOARD_DIRS=… just info-boards`).

### Callers switched to just

`.murdock`, `dist/tools/compile_and_test_for_board/compile_and_test_for_board.py`,
`dist/tools/ci/check_features_existing_inc_mk_is_up_to_date.sh`,
`dist/tools/doccheck/check.sh`, `dist/tools/compile_test/compile_like_murdock.py`,
`dist/tools/insufficient_memory/update_insufficient_memory_board.sh`,
`dist/tools/buildsystem_sanity_check/save_all_dependencies_resolution_variables.sh`,
`.github/workflows/test-on-iotlab.yml` (installs just for
`compile_and_test_for_board.py`), `.github/workflows/{test,deploy}-guides.yml` (new step installs just 1.59.0
with `taiki-e/install-action@v2`; `justfile` and `just/**` added to the path
filters), `.github/workflows/static-test.yml` (just installed on the runner and
mounted into the `riot/static-test-tools` container, which has no just yet),
`features.yaml` (comment), `features_yaml2mx.py` (generated hint text;
`makefiles/features_existing.inc.mk` regenerated), the zsh completion
(`list-ttys` removed from the make targets), and 14 documentation files.
Release notes and the generated changelog are historical and unchanged.

### Prerequisite

`just` must be installed (tested with 1.59.0; the justfiles use `import`,
`[group]`, `[doc]`, `[working-directory]`, `[no-exit-message]`,
`[positional-arguments]`). Make also needs it for `doc-ci` and for the base
directory goals `clean`, `distclean` and `info-applications-supported-boards`,
which read `APPS_BASE_DIRS` with `just --evaluate`; without just these stop
with an explicit error, the other base-directory goals (`docclean`,
`pkg-clean`, `static-test`, the pointer to just) and all application builds
work as before. The
CI images (riotbuild, static-test tools, Murdock workers) must provide just
before this can go upstream; the static-test workflow mounts it meanwhile.
`doc-ci` passes a command-line `DOCUMENTATION_FORMAT` on to just.

## Verification

Evidence: `.claude/research/test-logs/2026-11-12-p3-group1-just.md`.

- 122 cases, baseline `make <t>` (clean `0be9299ca9`) vs. `just <t>`, root
  and application context (`BOARD=native64`, `BOARD=native`): tool calls
  (doxygen, npm, riotgen via logging stand-ins) identical in every case;
  output identical apart from the documented deviations.
- `make <t>` fails for all 36 targets in every former context; untouched
  Make targets (`info-modules`, `help`, `clean`,
  `info-applications-supported-boards`) behave as before (`help` no longer
  lists the six removed targets `doc`, `doc-man`, `doc-latex`, `info-boards`,
  `info-emulated-boards`, `list-ttys`).
- `just --fmt --check --unstable`, `just --dry-run`, `git diff --check`,
  `dist/tools/buildsystem_sanity_check/check.sh`,
  `dist/tools/ci/check_features_existing_inc_mk_is_up_to_date.sh`: pass.

## Known deviations

Listed with reasons in the test log (section "Complete extraction"). In
short: Make's own recursion echo lines disappear; on failure paths just
reports the failing step's exit status (Make: always 2) and its own error
text; the welcome text points to just; generated hint texts say
`just generate-features`; no application-context checks and warnings;
values are data and are not re-parsed by the shell.

## Onboarding

```sh
just --list                 # all repository commands, grouped
just info-boards
just doc                    # Doxygen HTML
just DOCUMENTATION_FORMAT="html man" doc
cd examples/basic/default && make BOARD=native64   # applications: make
```

---

# Archive: rejected pilot (just → make bridges)

> **Superseded approach (2026-11-12, decision log D17):** the rest of this
> file documents the pilot branch. Its just → `_helper` bridges for
> group-2A/2C targets (`info-build`, `info-modules`, `info-features-*`,
> `help`, `reset`, `clean`, …) only put a just surface on top of Make and are
> **rejected**. Only its group-1 recipes were reused.

**Status:** Category 1 (Static Introspection) completed on the pilot branch;
see "Mapping to the workbook waves" for how it relates to the current plan
**Coordination branch:** `migration/category-1-static-introspection` at merge
`c9bc274f40` (documentation commit `d2c8865b6e`); `master` is still at the
upstream baseline `0be9299ca9`
**Initial baseline:** `a4863f6422` — `buildsystem: migrate static targets to just`

> **Note (2026-11-12, roadmap P0):** The pilot used the earlier
> "Tier 1 / 2A / 2B" labels and "categories". The current plan uses the
> five-group taxonomy (1/2A/2B/2C/3), the dispositions `MIGRATE`/`BRIDGE`
> from `riot_all_make_targets.xlsx`, and three waves (29 / 15 / 27). The
> target tool for groups 2A/2B/2C/3 is CMake + Ninja (compared hands-on with
> Meson + Ninja); the just → `_helper` bridges for group-2A targets are
> therefore **transitional** until a tool-independent resolver exists.

## Operating model

- **Tier 1 — Stateless:** direct `just` recipes over repository files or
  explicit environment values.
- **Tier 2A — Context-dependent:** retains RIOT Make context through private
  `_info-*` helpers until a real RIOT CMake configuration exists.
- **Tier 2B — Artifact-dependent:** remains Make-native until RIOT defines a
  CMake/Ninja artifact contract.

RIOT has no root `CMakeLists.txt` or `build.ninja`. Category 1 therefore does
not invent either system or add unrelated `cmake`/`ninja` gates. Tier labels
describe coupling; they do not imply a build-system replacement.

## Category 1 package results

| Package | Branch commit | Scope | Result |
|---|---|---|---|
| 1A static | `e55d22617c` | `info-boards`, `info-emulated-boards`, `info-applications` | Merged (`4c3b687adb`) |
| 1B contextual | `eb98e8ca9b` | Contextual `info-*` and board-support targets | Merged (`c9bc274f40`) |
| 1C artifacts | `a4863f6422` (unchanged) | `info-objsize`, `info-buildsize`, `info-buildsizes-diff` | Validated as intentionally Make-native |

Every merged package received independent auditor, reviewer, and tester
reports before merge. Package 1C was routed through the same gates and
confirmed to require no changes.

## Target mapping

| Legacy Make target | Implementation | Tier |
|---|---|---:|
| `info-boards` | Direct Just recipe; Make bridge forwards board state | 1 |
| `info-emulated-boards` | Direct Just recipe; Make bridge forwards board dirs | 1 |
| `info-applications` | Direct Just recipe; Make bridge forwards directory state | 1 |
| `info-build` | Just → `_info-build` private helper | 2A |
| `info-build-json` | Just → `_info-build-json` private helper | 2A |
| `info-modules`, `info-packages`, `info-cpu` | Just → private helper | 2A |
| `info-features-provided/required/missing/used` | Just → private helper | 2A |
| `info-kconfig-variables` | Just → private helper | 2A |
| `info-toolchains-supported` | Just → private helper | 2A |
| `check-toolchain-supported` | Just → private helper | 2A |
| `info-programmers-supported` | Just → private helper | 2A |
| `info-rust` | Just → private helper | 2A |
| `info-boards-supported` | Just → `_info-boards-supported` | 2A |
| `info-boards-features-missing` | Just → private helper | 2A |
| `info-boards-features-blacklisted` | Just → private helper | 2A |
| `info-boards-features-conflicting` | Just → private helper | 2A |
| `info-applications-supported-boards` | Just → `_info-applications-supported-boards` | 2A |
| `info-files` | Make-native (recursive `make -Bn` plus compiler probes) | 2A |
| `info-debug-variable-%` | Make-native (dynamic variable-name pattern) | 2A |
| `info-objsize` | Make-native | 2B |
| `info-buildsize` | Make-native | 2B |
| `info-buildsizes-diff` | Make-native | 2B |

Previously migrated utility targets remain bridged: `clean`, `pkg-clean`,
`print-versions`, `generate-features`, `list-ttys`, `reset`, `help`.

### Bridge contract

```text
make <public-target>
    └── just --working-directory "$(CURDIR)" <recipe>
            └── make --no-print-directory _<private-helper>   (Tier 2A only)
```

- Make bridges pass `--working-directory "$(CURDIR)"` so Just runs recipes in
  the invoking application directory, not the justfile directory.
- Just recipes call only private `_...` Make helpers or the original
  implementation; no public Make ↔ Just recursion exists.
- `info-build` and `info-build-json` unset Makefile-computed variables before
  entering Just so the child Make re-evaluates them exactly once instead of
  duplicating flags and include paths.
- `info-boards`, `info-emulated-boards`, and `info-applications` use
  definedness checks (`${VAR+x}`) to preserve explicitly empty and custom
  values.

## Mapping to the workbook waves

Generated on 2026-11-12 from this file's target mapping and sheet
`Migration Candidates` (RIOT `0be9299ca9`). Group/disposition/wave come from
the workbook; status comes from the pilot branch.

| Target | Pilot tier | Group | Disposition | Wave | Pilot status | Note |
|---|---|---|---|---|---|---|
| `info-boards` | 1 | 1 | MIGRATE | 1 | implemented | |
| `info-emulated-boards` | 1 | 1 | MIGRATE | 1 | implemented | |
| `info-applications` | 1 | 1 | MIGRATE | 1 | implemented | |
| `check-toolchain-supported` | 2A | 2A | MIGRATE | 2 | implemented (just → `_helper`) | |
| `info-build`, `info-build-json`, `info-modules`, `info-packages`, `info-cpu` | 2A | 2A | BRIDGE | 3 | implemented (just → `_helper`) | wave 3 done before waves 1/2 |
| `info-features-provided/required/missing/used` | 2A | 2A | BRIDGE | 3 | implemented (just → `_helper`) | wave 3 done before waves 1/2 |
| `info-kconfig-variables`, `info-toolchains-supported`, `info-programmers-supported`, `info-rust` | 2A | 2A | BRIDGE | 3 | implemented (just → `_helper`) | wave 3 done before waves 1/2 |
| `info-boards-supported`, `info-boards-features-missing/blacklisted/conflicting`, `info-applications-supported-boards` | 2A | 2A | BRIDGE | 3 | implemented (just → `_helper`) | wave 3 done before waves 1/2 |
| `info-files` | 2A | 2A | BRIDGE | 3 | Make-native | **conflict:** workbook `BRIDGE`, pilot Make-native |
| `info-objsize`, `info-buildsize`, `info-buildsizes-diff` | 2B | 2B | BRIDGE | 3 | Make-native | **conflict:** workbook `BRIDGE`, pilot Make-native |
| `info-debug-variable-%` | 2A | – | N/A (pattern rule) | – | Make-native | not a named target; outside the 71 |
| `clean`, `pkg-clean` | utility | 2C | MIGRATE | 2 | bridged | |
| `reset`, `help` | utility | 2A | MIGRATE | 2 | bridged | |
| `print-versions`, `list-ttys` | utility | 1 | MIGRATE | 1 | bridged | |
| `generate-features` | utility | 1 | OUT OF SCOPE | – | bridged | **conflict:** bridged although outside the 71 |

Open decisions (recorded in `.claude/research/decision-log.md`, D6–D10):
the four `info-files`/size conflicts, `generate-features`, and whether the
remaining wave-1 targets (doc, `welcome`) follow before any further wave-3 work.

## Verification evidence

Validated with `just 1.59.0` (static musl binary), GNU Make 4.3, and Bash
5.2.21:

```sh
just --list
just --dry-run <each recipe>
git diff --check
```

Byte-identical Make/Just parity in `examples/basic/hello-world` for:

- `info-build`, `info-build-json`
- `info-cpu`, `info-modules`, `info-packages`
- `info-features-provided/required/missing/used`
- `info-kconfig-variables`
- `info-toolchains-supported`, `info-programmers-supported`
- `info-boards-supported`
- `help`, `list-ttys`

Root-level checks passed:

- `make BOARDS= info-boards` preserves the empty value.
- `make BOARDS='a b' info-boards` preserves a custom value.
- `make EXTERNAL_BOARD_DIRS=... info-emulated-boards` discovers external
  boards by name.
- `make APPLICATION_DIRS=... info-applications` preserves overrides.
- `make APPLICATION_DIRS=... info-applications-supported-boards` matches its
  private helper.
- `make -n clean` emits only recursive clean operations, no compiler or linker
  invocations.
- Recursion scan: `justfile` contains no call to a public `make info-*` target.

## Known deviations

- Failure paths add bridge frames. For example, `make reset` without hardware
  exits with the same status as before but prints the child Make error plus the
  Just/parent-Make frame. Successful-output parity is exact.
- `info-files` remains Make-native because its recursive `make -Bn` and
  compiler `-MM` probes add a Make recursion level when bridged.
- `info-debug-variable-%` remains Make-native because forwarding arbitrary
  values through the environment changes shell backslash/quote handling.
- Artifact targets intentionally remain Make-native; migration requires a
  defined artifact contract covering board identity, `BINDIR` layout, ELF
  paths, per-module object directories, and missing-artifact behavior.

## Onboarding

From the repository root:

```sh
just --list
just info-boards
just info-applications
make info-boards
```

From an application directory:

```sh
make BOARD=native64 info-build
just --working-directory "$PWD" info-build
```

`just` locates the root justfile by searching upward; always pass
`--working-directory "$(CURDIR)"` from Make bridges so application context is
preserved. Use `make -n <target>` to inspect a bridge without executing it.

## Next categories

Category 1 established the bridge and validation pattern. Later categories
(Auditing, HIL-Interaction, Synthesis, Reduction) should reuse it and must not
merge without auditor, reviewer, and tester evidence.
