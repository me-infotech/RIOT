---
name: migration-review
description: Review checklist for RIOT Make→just migration diffs (group-1-only scope, no Make in just, output fidelity, Make goal semantics) plus general correctness. Use when reviewing uncommitted changes to justfile, Makefile*, *.mk or MIGRATION.md in RIOT_Test.
---

# Migration Review

Review changes, not the repository. Cite `file:line` for every finding.
Never edit files and never run git write commands.

## 1. Establish scope

- Uncommitted: `git status --short`, `git diff`, `git diff --staged`.
- Branch comparison (read-only): `git diff <base>...<branch>`.
- State the goal of the change in one sentence and the target list it claims.

## 2. Migration-specific checklist

### Scope
- Every just recipe belongs to `.claude/research/just-scope.md` A/B (group 1).
  A 2A/2B/2C/3 target in the justfile is a **Blocker**, whatever the workbook
  disposition says (D17). Section C stays in Make (D18).
- No unnamed declaration (`CLEAN--*`, pattern, path) turned into a recipe.
- The diff carries a group-1 proof per target (recipe, prerequisites, called
  scripts, `file:line`).

### No Make in just
- `grep -nE '(^|[^-_a-z])(make|\$\(MAKE\)|gmake)([^-_a-z]|$)' justfile` →
  no hit outside comments. Any `make`/`_helper` call is a **Blocker**.
- Scripts called by recipes do not run Make (e.g. `static_tests.sh` does).
- No Make-computed input (`BOARD`, `CPU`, `USEMODULE`, `BINDIR`, `ELFFILE` …).

### Complete extraction (D20)
- No rule, forward or `.PHONY` entry for a migrated target remains in any
  Makefile; `make <target>` fails.
- Every RIOT caller (scripts, CI, `.murdock`, workflows, docs) uses just.
- Settings only in `just/settings.just`; Make reads shared values with
  `just --evaluate`.

### Semantics that are easy to break
- `MAKECMDGOALS` filters: `Makefile.include:117` (`CLEAN`) and `:908`
  (`clean distclean generate-Makefile.ci help`). Public target names must
  survive so these filters still match.
- `?=` defaults and explicitly empty variables (`BOARDS=`) — check `${VAR+x}`
  handling in recipes.
- Exit status and stderr on failure paths (bridge adds frames → document).
- Sort order, trailing spaces/newlines (`tr '\n' ' '; echo`), quoting.
- No variable-computing include removed; no `Makefile.dep`/`Makefile.features`
  logic duplicated in just.

### Concept consistency
- Change matches the current roadmap phase and its gate.
- `MIGRATION.md` updated only for tested targets; group labels agree with
  the workbook, scope with `just-scope.md`.

## 3. General checks (short)

Correctness of edge cases, shell injection via unquoted variables, absolute
host paths, SPDX headers on new files, tabs in Makefiles, no dead code.

## Severity and output

| Level | Meaning |
|---|---|
| Blocker | breaks `make <target>`, Make call in just, non-group-1 target in just, build step added |
| Major | output/exit differs silently, missing test evidence |
| Minor | low-impact issue |
| Nit | style, optional |

```markdown
## Summary
## Findings
### [Blocker|Major|Minor|Nit] <title>
`path:line` — what, why, concrete fix
## Questions
## Verdict: LGTM | CHANGES REQUESTED
```

Do not invent problems. If the diff is too large to review well, propose a split.
