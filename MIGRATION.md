<!--
SPDX-FileCopyrightText: 2026 RIOT contributors
SPDX-License-Identifier: LGPL-2.1-only
-->

# RIOT Build-System Migration

**Status:** Category 1 (Static Introspection) completed
**Coordination branch:** `master` at merge `c9bc274f40`
**Initial baseline:** `a4863f6422` — `buildsystem: migrate static targets to just`

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
