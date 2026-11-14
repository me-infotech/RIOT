# target_taxonomy — reproducible classification of make targets

Puts every named make target into one of five groups, by fixed rules:

| Group | Meaning |
|---|---|
| 1 | stateless: no application/board context, no build, no artifact |
| 2A | needs the resolved make context (`BOARD`, `CPU`, `USEMODULE`, …) |
| 2B | reads an existing artifact or runtime resource (ELF, flasher, terminal) |
| 2C | manages the artifact lifecycle (deletes or installs artifacts) |
| 3 | starts a build (compiler, linker, build graph, host-tool build) |

## How it works

For each target the script reads GNU Make's database (`make -pRrq`) of a
fixed context (directory, `BOARD=nrf52840dk`, fallback `BOARD=native64` for
targets the reference board does not define) and checks the recipe of the
target and of all its prerequisites. The first rule that applies, in the
order 3 > 2C > 2B > 2A > 1, decides; the strongest result of the
prerequisites wins.

| Rule | Group | Signal |
|---|---|---|
| B1 | 3 | a compiler/linker variable (`CC`, `LINK`, `AR`, …) is run as a command |
| B2 | 3 | a build command (`cmake`, `gcc`, `cargo build`, `ninja`, …) is run |
| B3 | 3 | sub-make in another directory with its default goal |
| B4 | 3 | `all`, `link`, `pkg-build` or another build-graph target is a prerequisite |
| B5 | 3 | sub-make of `Makefile.base` / `MODULE=` (module compile) |
| B6 | 3 | a build product (`.elf`, `.hex`, `.bin`, `.o`, `.a`, …) is a prerequisite |
| B7 | 3 | a repository script called by the recipe runs `make … all` or `cmake` |
| L1 | 2C | the recipe deletes files (`rm -r`/`rm -f`, `$(RM)`, `git clean`) |
| R1 | 2B | the recipe uses an artifact/runtime variable (`ELFFILE`, `TERMPROG`, `FLASHER`, `PORT`, …) |
| S1 | goal's group | sub-make with explicit goals: the group of those goals |
| K1 | 2A | the recipe uses a context variable (`BOARD`, `CPU*`, `FEATURES_*`, `USEMODULE`, `PKG_*`, …) |
| K2 | 2A | the recipe uses a variable whose value differs between `nrf52840dk` and `native64` (values that change between two runs, e.g. time stamps, are excluded) |
| K3 | 2A | the recipe re-runs make in the same context without goals (`help`) |
| S0 | 1 | none of the above |
| N0 | ? | the target is not defined in any known context |

The rules are the decision rules of the target inventory
(`riot_all_make_targets.xlsx`, sheet "Group & Category Definitions") written
as code. `APP_VER` is fixed to `0` so that two runs give identical output.

## Usage

```sh
# classify the inventory (reference groups in inventory.csv), write a CSV
dist/tools/target_taxonomy/target_taxonomy.py classify --output rules.csv
# agreement with the reference groups, Cohen's kappa, confusion matrix
dist/tools/target_taxonomy/target_taxonomy.py compare rules.csv --list
# CI: targets declared since the base branch that are not in inventory.csv
dist/tools/target_taxonomy/target_taxonomy.py check-new --base master
```

`check-new` is run by `dist/tools/ci/check_new_make_targets.sh` from
`static_tests.sh`. A new target is classified by the same rules; a target
that is not callable in any known context is reported as such. Add new
targets to `inventory.csv` with their group.

`inventory.csv` is exported from `riot_all_make_targets.xlsx` (sheet
"Named Targets", RIOT `0be9299ca9`): target, reference group, scope,
evidence. Targets that were moved to `just` (roadmap P3) are no longer make
targets in this tree; classify against a checkout of `0be9299ca9`
(`--repo`).

Requirements: Python 3 (standard library only), GNU Make, git.
