# Test log 2026-11-14 — rule-based, reproducible target classification (D22/D23)

Tool: `dist/tools/target_taxonomy/target_taxonomy.py` (working tree, uncommitted).
Reference checkout: `/home/mohammadjavad/Documents/RIOT` @ `0be9299ca9`
(only `make -pRrq` runs; `git status` before/after identical).
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
| agreement | 242/323 = 0.749 |
| Cohen's kappa | 0.650 |
| not defined in any context (N0) | 21 |

Confusion matrix (rows = workbook, columns = rules):

| ref \ rules | 1 | 2A | 2B | 2C | 3 | ? |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 54 | 1 | 0 | 0 | 1 | 1 |
| 2A | 15 | 23 | 3 | 5 | 2 | 4 |
| 2B | 9 | 2 | 27 | 1 | 1 | 4 |
| 2C | 1 | 2 | 0 | 8 | 1 | 0 |
| 3 | 8 | 7 | 1 | 0 | 130 | 12 |

Development history (same 323 targets): 0.192 (first run against
`RIOT_Test`, where the group-1 targets moved to just no longer exist) →
0.344 (clean reference checkout) → 0.483 → 0.638 → 0.746 → 0.749. Rule
changes were made for classes of recipes (sub-make detection, package
module rules, command position), not for single targets.

Main classes of the 81 differences (list in `compare.txt`):
- N0 (21): targets that exist only in contexts the script does not build
  (e.g. `tests/build_system/cortexm_common_ldscript` needs a Cortex-M ROM
  layout variable, iotlab/openvisualizer make files, `makefiles/utils/*.mk`).
- 2A → 1 (15): context only visible at parse time (`$(info …)` under a goal
  condition, e.g. `info-boards-supported`) or in a called script
  (`help`, `compile-commands`, `mcuboot-create-key`).
- 2B → 1 (9): runtime only in an external script/program (`bench`,
  `fido2-test`, `run`) or empty hook targets (`preflash`, `termdeps`).
- 3 → 1/2A (15): host-tool builds behind variables the rules do not expand
  (`mosquitto_rsmb`, `zep_dispatch`), `test*` targets (workbook rule
  "Test-Guards" puts them into 3 by name).
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
