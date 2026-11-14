# Test log 2026-11-14 — rule-based, reproducible target classification (D22/D23)

Tool: `dist/tools/target_taxonomy/target_taxonomy.py` (working tree, uncommitted).
Reference checkout: `/home/mohammadjavad/Documents/RIOT` @ `0be9299ca9`
(only `make -pRrq` runs; `git status` before/after identical. Note from the
review: `make -q` can still remake included makefiles that have a rule; in
RIOT nothing was written, checked with `git status` and `find -newer`).

**Numbers below are after the review fixes (section "Review").** The first
version (commit `099abbd00c`) had agreement 0.749 / kappa 0.650.
Board: `nrf52840dk` (D22), fallback `native64`. Evidence:
`.claude/research/taxonomy-rules/` (`rules-0be9299ca9-nrf52840dk.csv`,
`compare.txt`, `commands.txt`, `SHA256SUMS`).

## Reproducibility

- Two runs of `classify`: byte-identical CSV (`cmp`). An earlier version
  differed in evidence text only (time stamp in `APP_VER`, from
  `makefiles/suit.inc.mk:10`); fixed by `APP_VER=0`.
- K2 drops variables whose value differs between two runs with the same
  board (time stamps in `makefiles/utils/test-variables.mk`).

## Agreement with the manual classification (workbook, 323 targets)

| | Value |
|---|---|
| agreement | 255/323 = 0.789 |
| Cohen's kappa | 0.704 |
| not defined in any context (N0) | 21 |

Confusion matrix (rows = workbook, columns = rules):

| ref \ rules | 1 | 2A | 2B | 2C | 3 | ? |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 55 | 1 | 0 | 0 | 0 | 1 |
| 2A | 13 | 26 | 3 | 5 | 1 | 4 |
| 2B | 9 | 2 | 27 | 1 | 1 | 4 |
| 2C | 0 | 2 | 0 | 9 | 1 | 0 |
| 3 | 4 | 3 | 1 | 0 | 138 | 12 |

Development history (same 323 targets): 0.192 (first run against
`RIOT_Test`, where the group-1 targets moved to just no longer exist) →
0.344 (clean reference checkout) → 0.483 → 0.638 → 0.746 → 0.749
(commit `099abbd00c`) → 0.789 (review fixes). Rule
changes were made for classes of recipes (sub-make detection, package
module rules, command position), not for single targets.

Main classes of the 68 differences (list in `compare.txt`):
- N0 (21): targets that exist only in contexts the script does not build
  (e.g. `tests/build_system/cortexm_common_ldscript` needs a Cortex-M ROM
  layout variable, iotlab/openvisualizer make files, `makefiles/utils/*.mk`).
- 2A → 1 (13): context only visible at parse time (`$(info …)` under a goal
  condition, e.g. `info-boards-supported`) or in a called script
  (`help`, `compile-commands`, `mcuboot-create-key`).
- 2B → 1 (9): runtime only in an external script/program (`bench`,
  `fido2-test`, `run`) or empty hook targets (`preflash`, `termdeps`).
- 3 → 1/2A (7): build steps hidden in scripts or tools the rules do not
  read (`generate-Makefile.ci`, `compressed-image`, `hello.wasm`,
  `clang-tidy`, `softcore_c`, `riotboot/flash-bootloader`,
  `build-system-utils-tests`).
- 2A → 2C (5): deletion of stamp/temp files (`prepare`,
  `info-boards-features-*`) counted as lifecycle.

Which side is right is open: the differences are the input for the
adjudication in roadmap P1 (second coder, kappa).

## New targets (CI check)

Clone of the reference in the scratchpad, five synthetic targets added to
`examples/basic/hello-world/Makefile`:

| Target | Recipe | Result |
|---|---|---|
| `say-hello` | `@echo hello` | 1 [S0] |
| `show-board-cpu` | `@echo $(BOARD) $(CPU)` | 2A [K1] |
| `size-report` | `$(SIZE) $(ELFFILE)` | 2B [R1] |
| `drop-bindir` | `rm -rf $(BINDIR)/extra` | 2C [L1] |
| `build-and-say` | prerequisite `all` | 3 [B4] |

`check-new --base HEAD`: all five reported with the expected group, exit 1;
clean tree: "no new targets", exit 0. `dist/tools/ci/check_new_make_targets.sh`
in `RIOT_Test` against `master`: exit 0. Run time of `check-new`: < 1 s.
Bug found and fixed on the way: ERE has no `\t` escape (`[^\t]` excluded
the letter `t`; `size-report` was missed).

Not tested: a run of `static_tests.sh` as a whole (tools missing on the
host).

## Review (2026-11-14) and fixes

Independent review (subagent, read-only) of `099abbd00c`: 5 Major,
9 Minor, 4 Nit. Reproducibility confirmed (reviewer's run byte-identical
to the stored CSV). Fixed in the working tree:

| Finding | Fix | Verified |
|---|---|---|
| M: absolute prerequisites never matched their rule (227/247 lost in hello-world) | prerequisites normalised like target names | `mosquitto_rsmb` 1 → 3 [B3] |
| M: cycle results cached, order-dependent | results computed while a cycle cut the search are not cached | mini Makefile `a: b`/`b: a`: same groups in both orders |
| M: "functional" only meant "name in the database" | `check-new` dry-runs `make -n <target>` and prints the error | `broken-target` (missing prerequisite) and a "missing separator" file → `make -n FAILED` with make's message |
| M: CI hook in `68ba8f4a7b`, script only in `099abbd00c` (bisect) | open: needs a rewrite of the two local commits (user decision) | — |
| M: `*Makefile*` matched patch files | pathspec `Makefile*`, `*/Makefile*`, `*.mk`, `:!*.patch` | patch with `From`/`Subject` lines → not reported |
| m: `define` bodies, `-include` counted | skip `define … endef` and names starting with `-` | `define` body line → not reported |
| m: unknown `--base` gave bogus targets | `git rev-parse --verify`, exit 2 | `--base nosuchrev` → error, exit 2 |
| m: git config (`grep.column`) changed the output | `git -c grep.column=false …`, `LC_ALL=C` | `GIT_CONFIG_*` with `grep.column=true` → same result |
| m: absolute paths in evidence | relative paths | `grep -c /home/` on the CSV → 0 |
| m: workbook rules for tests/install missing | T1 (test scripts) and I1 (`install -`) | `test`, `test-as-root`, `test-with-config` → 3; `install` → 2C; `test/available`, `*/check-config` stay 2A |
| m: `env`/`sudo` wrappers, compiler queries | wrappers allowed at command position; `--version`, `-dump*`, `-print-*` excluded | `zep_dispatch` → 3 |
| m: B7 matched a version listing of `cmake` | B7 needs `cmake --build/-S/-B` | `print-versions` → 1 |
| m: CI script used `CI_BASE_BRANCH`, base tip, one message for all errors | `$1` = `BASE_BRANCH`, merge base, separate message for exit ≠ 1 | clone: exit 0/1/2 as documented |
| Nits: `make` missing in DEPS, summary on stderr, flake8 E306 | fixed | — |
| Nit: inventory group not checked against rules, removed targets not reported | documented as limitation (README) | — |

`npm ci` (doc site) is not counted as install (I1): tool provisioning of
the documentation, consistent with `just-scope.md` A.
