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
| B1 | 3 | a compiler/linker variable (`CC`, `LINK`, `AR`, …) is run as a command (not `--version`, `-dump…`, `-print-…`) |
| B2 | 3 | a build command (`cmake`, `gcc`, `cargo build`, `ninja`, …) is run |
| B3 | 3 | sub-make in another directory with its default goal |
| B4 | 3 | `all`, `link`, `pkg-build` or another build-graph target is a prerequisite |
| B5 | 3 | sub-make of `Makefile.base` / `MODULE=` (module compile) |
| B6 | 3 | a build product (`.elf`, `.hex`, `.bin`, `.o`, `.a`, …) is a prerequisite |
| B7 | 3 | a repository script called by the recipe runs `make … all`, `cmake --build/-S/-B` or `cargo build` |
| T1 | 3 | the recipe runs the application's test scripts (`$(TEST_EXECUTOR)`, `for t in $(TESTS…)`) |
| I1 | 2C | the recipe installs files (`install -…`) |
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
A command position may start with `env …`, `sudo`, `nice`, `command` or
`exec`. Results that depend on where a dependency cycle is entered are not
cached, so the order of the targets does not change a result.

## Hardware attribute (D22 point 7)

`classify` also writes `hardware` (yes / no / ? when the target was not
found) and `hardware_evidence`, independent of the group. A target needs
hardware if its recipe, at any expansion level, or one of its
prerequisites runs `$(FLASHER)`, `$(DEBUGGER)`, `$(DEBUGSERVER)`,
`$(DEBUGCLIENT)`, `$(RESET)`, `$(TERMPROG)` or `$(PROGRAMMER)` at a command
position, runs an `iotlab-*` command (remote testbed), runs the
application's tests, or runs a sub-make with a goal such as `flash`/`term`.
Targets found only in a `native*` context run on the host and count as
`no`. Not covered: pattern rules whose goal is only known at run time
(`riotboot/bootloader/%` with `$*`).

## Usage

```sh
# classify the inventory (reference groups in inventory.csv), write a CSV
dist/tools/target_taxonomy/target_taxonomy.py classify --output rules.csv
# agreement with the reference groups, Cohen's kappa, confusion matrix
dist/tools/target_taxonomy/target_taxonomy.py compare rules.csv --list
# CI: targets declared since the base branch that are not in inventory.csv
dist/tools/target_taxonomy/target_taxonomy.py check-new --base master
```

`check-new` is run by `dist/tools/ci/check_new_make_targets.sh
"${BASE_BRANCH}"` from `static_tests.sh`. It compares the working tree with
the merge base of the base branch and `HEAD`. A new target is classified by
the same rules and dry-run with `make -n <target>` in the context where it
was found (this shows that make accepts it, e.g. no missing prerequisite or
syntax error; it does not run the recipe). Add new targets to
`inventory.csv` with their group. Exit status: 0 no new targets, 1 new
targets, 2 error (e.g. base revision not fetched).

Limitations:
- Targets whose name comes from a variable (`$(NEWT):`) are not found by
  the scan; lines inside `define … endef` and patch files are skipped.
- The group written into `inventory.csv` is not compared with the rules,
  and removed targets are not reported.
- `make -pRrq` still remakes included makefiles that have a rule (GNU Make
  behaviour); run it in a CI or scratch checkout.
- Signals hidden in external programs or scripts (other than one level of
  repository scripts for B7) are not seen.

`inventory.csv` is exported from `riot_all_make_targets.xlsx` (sheet
"Named Targets", RIOT `0be9299ca9`): target, reference group, scope,
evidence. Targets that were moved to `just` (roadmap P3) are no longer make
targets in this tree; classify against a checkout of `0be9299ca9`
(`--repo`).

Requirements: Python 3 (standard library only), GNU Make, git.
