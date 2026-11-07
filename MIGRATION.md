<!--
SPDX-FileCopyrightText: 2026 RIOT contributors
SPDX-License-Identifier: LGPL-2.1-only
-->

# RIOT Build-System Migration

**Status:** Category 1 (Static Introspection) in progress  
**Baseline:** `a4863f6422` — `buildsystem: migrate static targets to just`

## Operating model

- **Tier 1 — Stateless:** direct `just` recipes over repository files or
  explicit environment values.
- **Tier 2A — Context-dependent:** retains RIOT Make context through private
  helpers until a real RIOT CMake configuration exists.
- **Tier 2B — Artifact-dependent:** remains Make-native until RIOT defines a
  CMake/Ninja artifact contract.

RIOT has no root `CMakeLists.txt` or `build.ninja`; Phase 1 does not invent
either system or add unrelated `cmake`/`ninja` gates.

## Package status

| Package | Worktree | Scope | Status |
|---|---|---|---|
| 1A | `migration-cat1-static` | `info-boards`, `info-emulated-boards`, `info-applications` | Fix committed as `e55d22617c`; validation rerun pending |
| 1B | `migration-cat1-context` | Make-contextual `info-*` targets and board-support introspection | Developer fixes pending; auditor/reviewer found blockers |
| 1C | `migration-cat1-artifacts` | `info-objsize`, `info-buildsize`, `info-buildsizes-diff` | Intentionally unchanged; auditor/reviewer/tester passed |

No package may merge without independent auditor, reviewer, and tester
approval. The `just` executable is unavailable in the current environment;
native Just parser/runtime checks are therefore pending.

## Target mapping

| Legacy Make target | Just/bridge | Tier | Preconditions |
|---|---|---:|---|
| `info-boards` | `just info-boards` | 1 | Board directories and board variables |
| `info-emulated-boards` | `just info-emulated-boards` | 1 | Board directories and board variables |
| `info-applications` | `just info-applications` | 1 | Repository application directories |
| `info-build`, `info-build-json` | `just` → private Make helper | 2A | Evaluated application/board context |
| `info-modules`, `info-packages`, `info-cpu` | `just` → private Make helper | 2A | Evaluated Make variables |
| `info-features-*`, `info-kconfig-variables` | `just` → private Make helper | 2A | Evaluated feature/Kconfig context |
| `info-boards-supported`, `info-boards-features-*` | `just` → private Make helper | 2A | Board-candidate support evaluation |
| `info-objsize`, `info-buildsize`, `info-buildsizes-diff` | Make-native | 2B | Existing object/ELF artifact contract |

## Verification gates

Each branch must provide:

1. Target-scope and non-compilation inventory.
2. `git diff --check` and static/recursion scans.
3. `make -n` bridge verification.
4. Make/Just output parity where `just` is available.
5. Independent auditor, reviewer, and tester reports.

Current successful evidence:

- Artifact package: read-only Make checks passed; worktree clean; no changes
  required because artifact paths and semantics are Make-computed.
- Static package: Make bridge and variable-propagation checks passed; quoting
  fix committed after review finding; final gate rerun is pending.

## Onboarding

From the repository root:

```sh
just --list
just info-boards
just info-applications
make info-boards
```

Use `make -n <target>` to inspect a legacy bridge. Never make a public Just
recipe call a public Make target that forwards back to the same recipe; use a
private `_...` helper when Make-computed state is required.

## Open items

- Revalidate the static branch after the quoting fix.
- Fix and revalidate contextual private-helper inclusion and Make-state
  propagation.
- Merge only branches with all three approval reports.
- Install `just` or provide an equivalent CI environment for native Just
  syntax, dry-run, and runtime parity checks.
