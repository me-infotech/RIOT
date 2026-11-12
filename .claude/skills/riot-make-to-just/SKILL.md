---
name: riot-make-to-just
description: Move RIOT OS group-1 make targets (stateless — no Make context, no artifact, no runtime, no artifact lifecycle, no build) completely into the root justfile, with no call back into make. Scope list in .claude/research/just-scope.md (36 targets). Use when implementing, reviewing or testing a task-layer migration step in RIOT_Test.
---

# RIOT Make to just migration (task layer, group 1 only)

Act as a precise build-system engineer for GNU Make and the `just` command
runner. Purpose of the migration: **take responsibilities out of Make.** A just
recipe that calls Make only adds a surface on top of Make and moves nothing —
that is rejected (user rule 2026-11-12, decision log D17).

## Hard rules

1. **Scope = `.claude/research/just-scope.md`, sections A and B (36 targets).**
   Section C (`doc-ci`, `static-test`) stays in Make for now (user, D18).
   Sections C, D and E, and every target of groups 2A/2B/2C/3, never go into the justfile —
   whatever the workbook disposition (`MIGRATE`/`BRIDGE`, waves 2/3) says.
2. **No Make in just.** No `make`, `$(MAKE)`, `make -f …`, `_helper` targets,
   and no script whose job is to run Make. Re-implement the logic in the
   recipe (shell or the existing Python/shell tool the Makefile calls).
3. **No Make-computed input.** Inputs come from repository files, environment
   variables or recipe parameters only.
4. **Extract completely (user, 2026-11-12, D20):** a migrated target keeps
   no entry in any Makefile — no rule, no forward, no `.PHONY` entry. RIOT's
   own callers (scripts, CI, `.murdock`, GitHub workflows, documentation) are
   switched to `just`. A remaining Make target may call a just recipe
   (`doc-ci`, starlight `install`); just never calls Make.
4a. **Behaviour stays the same:** the recipe does exactly what the Make
   target did for the same inputs (proved by byte parity against the clean
   checkout). Inputs that Make took from its command line only (`:=` in the
   Makefile) are just settings (`just NAME=value <recipe>`); inputs Make took
   from the environment (`?=`) are read from the environment.
4b. **One configuration file:** every constant, default and input lives in
   `just/settings.just`; recipe files contain only steps. Values Make still
   needs are read from there with `just --evaluate NAME` (no copies).
4c. **Layout:** the root `justfile` only sets the shell and imports
   `just/settings.just` and one file per group (`just/repository.just`,
   `just/generate.just`, `just/doc.just`) with `import`, so recipe names stay
   unprefixed.
5. Nothing is committed. The user reviews every change. Work in the
   `RIOT_Test` working tree on `master`; only your own uncommitted changes may
   appear there.
6. Proof-of-concept boards: `native64` and `native` only (D16) — relevant only
   for app-context invocations such as `make -C examples/basic/hello-world
   BOARD=native64 info-boards`.

### State (2026-11-12)

- `just 1.59.0` in `~/.local/bin`; the justfile is tested with this version
  only and uses `[group]`, `[doc]`, `[working-directory]`,
  `[no-exit-message]`.
- **Implemented (P3, uncommitted, `RIOT_Test` master):** all 36 targets of
  `just-scope.md` A+B are in `just/*.just` and removed from every Makefile;
  callers and docs use just. Evidence:
  `.claude/research/test-logs/2026-11-12-p3-group1-just.md`.
  The older untracked justfile (just → `_info-*` calls) was replaced; its
  content is preserved in branch `migration/category-1-static-introspection`.
- Branch `migration/category-1-static-introspection` (worktree
  `RIOT_Test-pilot`) is the **rejected** pilot (just → `_helper` bridges for
  2A/2C). Read it only as a counter-example; reusable from it: the group-1
  recipes `info-boards`, `info-emulated-boards`, `info-applications`
  (byte-order sort fix D14).

## Procedure

1. **Pick targets** from `just-scope.md` A/B. For each, find every declaration
   (`grep -rnE "^<target>[[:space:]]*:" --include=Makefile* --include=*.mk`).
   Same name in another context with another group (e.g. `static-test` in
   `tests/build_system/xfa`) → leave that one alone.
2. **Prove group 1 from source**, not from the sheet: read recipe and
   prerequisites recursively. Stop and report if you find any of: `$(MAKE)`
   (also inside called scripts), a Make-computed variable, a prerequisite that
   builds/deletes artifacts, or registration in `BUILDDEPS`/`TERMDEPS`/
   `FLASHDEPS`.
3. **Flatten Make levels.** Root targets often recurse (`doc` →
   `$(MAKE) -C doc/doxygen`). The just recipe contains the final commands of
   every level; recipe dependencies replace Make prerequisites.
4. **Extract the exact shell logic**: flags, quoting, `echo`/`printf`
   formats, sort order, error text, exit status. Read it, do not paraphrase.
5. **Write the recipe** in the group file under `just/` with the translation
   rules below; new settings go to `just/settings.just`. Names: recipes from `doc/doxygen/Makefile` and
   `doc/starlight/Makefile` are `doxygen-<target>` / `starlight-<target>`
   (`doxygen-version`, `graphviz-check` keep their names); all others keep
   the Make name.
6. **Remove the target from Make** (rule 4): delete the rule, its `.PHONY`
   entry and variables only it used; keep variable machinery that remaining
   targets need (`ALLBOARDS`, `APPLICATION_DIRS` feed `clean` and group-2A
   targets). Switch every caller found with
   `git grep -nE "make[^|;]*\b<target>\b"` (scripts, CI, docs; not release
   notes) to `just <recipe>` (`just --justfile "$RIOTBASE/justfile"` from
   other directories). Recipes run in the RIOT root; recipes that need the
   caller directory use `$_RIOT_JUST_CALLER`. Values reach scripts through
   exported environment variables or arguments, never as pasted text.
7. **Verify** with `.claude/skills/riot-make-to-just/parity_check.sh`:
   - `just --list`, `just --dry-run <recipe>`.
   - Byte parity (stdout, stderr, exit) of baseline `make <t>` (clean RIOT)
     vs. candidate `just <t>`, and candidate `make <t>` must fail; root and,
     where the target exists there, `examples/basic/hello-world` with
     `BOARD=native64` and `BOARD=native`.
   - Overrides: empty and custom values (`BOARDS=`, `BOARDS='a  b'`,
     `EXTERNAL_BOARD_DIRS=…`, `APPLICATION_DIRS=…`).
   - **Make-free check:** `grep -nE '(^|[^-_a-z])(make|\$\(MAKE\)|gmake)([^-_a-z]|$)' justfile`
     must return nothing except comments; check every script a recipe calls.
   - Generated files (`doc/guides/generated/*`, `feature_list.md`,
     `features_existing.inc.mk`): `git status --short` and content diff equal
     to baseline.
8. **Report** in the output format below.

## Make → just translation rules

| Make | just |
| --- | --- |
| `.PHONY: x` | Nothing; recipes always run |
| target with prerequisites | recipe dependencies `x: a b` |
| file rule with timestamp (`src/changelog.md: …`) | regenerate every run, or `[script]` with an explicit `-nt` check |
| `$(VAR)` from the environment | `env_var_or_default("VAR", "fallback")`; definedness: `${VAR+x}` in a shebang recipe |
| `$(CURDIR)` | `justfile_directory()` for root targets (recipes run there); `invocation_directory()` where Make used the caller directory |
| `$(RIOTBASE)` | `justfile_directory()` |
| `$(shell …)` / `$(wildcard …)` | shebang recipe |
| `$(sort …)` | `LC_ALL=C sort -u`, joined without trailing space (`echo $list`) |
| `@cmd` | default silent line with `@`, or shebang recipe |
| `-@cmd` | linewise: `-` prefix; shebang: `cmd \|\| true` |
| `$(COLOR_ECHO) "$(COLOR_RED)…"` | `printf` with the same escape codes; respect `CC_NOCOLOR` like `color.inc.mk` |
| `$$var` | `$var` in a shebang recipe |
| `$(call sh_echoerr,…)` | `echo "…" >&2` |
| internal step | `[private]` |
| destructive step | `[confirm]` (group 1 has none today) |

Use `set shell := ["bash", "-ec"]`; no `-u` (optional variables). Shebang
recipes: `set -e`, add `-f` while expanding untrusted lists.

## Worked example: `doc` (two Make levels → one recipe)

Make today: `Makefile:9` runs `features_yaml2mx.py … --output-md
doc/doxygen/src/feature_list.md` and then `$(MAKE) -C doc/doxygen doc`, which
runs `graphviz-check`, `html` (needs `src/changelog.md`) and
`doxygen-version`, and exports `STRIP_FROM_INC_PATH_LIST`.

```just
# Generate the HTML documentation (Doxygen).
doc: _doc-feature-list doc-graphviz-check (_doxygen "HTML") doc-doxygen-version

[private]
_doxygen format:
    #!/usr/bin/env bash
    set -e
    root={{justfile_directory()}}
    cd "$root/doc/doxygen"
    export STRIP_FROM_INC_PATH_LIST=$(git ls-tree -dr --full-tree --name-only HEAD core drivers sys \
        | grep '/include$' | sed "s|.*|\"$root/&\"|")
    ./generate-changelog.py src/changelog.md.tmp ../../release-notes.txt src/changelog.md
    ( cat riot.doxyfile; echo "GENERATE_{{format}} = yes" ) | "${DOXYGEN:-doxygen}" -
```

Check the exact `sed` quoting and messages against `doc/doxygen/Makefile`
before using this; it is a pattern, not a verified recipe.

## Not allowed — examples from the rejected pilot

```just
# WRONG: just as a surface on Make (rule 2)
info-build-json:
    @make --no-print-directory _info-build-json
```

`info-build`, `info-modules`, `info-features-*`, `help`, `reset`, `clean`,
`pkg-clean`, `check-toolchain-supported` … are 2A/2C. They stay Make-native
until the build/configuration layer takes them over (roadmap P4–P6).

## Output format

Per target:

- **Target:** [name] — just-scope section [A/B], workbook disposition [as in sheet]
- **Group-1 proof:** [recipe + prerequisites read, `file:line`; scripts checked]
- **File:** [Makefile path]
- **Original Code (Lines X-Y):** [code]
- **Forward (Makefile):** [code]
- **just recipe:** [code]

Then: verification commands and results (parity table, Make-free grep),
the list of switched callers, any target that turned out **not** to be
group 1 (with evidence, so `just-scope.md` can be corrected), and
`git status --short` / `git diff --stat`. Nothing committed.
