Flash without Make: programmer data (migration step G3-2)
==========================================================

`just flash <application> <board>` does what GNU Make's target `flash` does:
it builds the application (`all`, without Make: `just build`, step G3-1) and
runs the flasher of the programmer with the arguments and the environment
Make gives it. Inputs are **data only**: the YAML data of the repository,
the resolver (G0-2), the build data (G3-1) and the flash data of this step.
No make process is started, no Make file is opened, no Make syntax is parsed.

```sh
just flash examples/basic/hello-world nrf52840dk                     # the board's default programmer
just flash examples/basic/hello-world nrf52840dk PROGRAMMER=openocd  # VAR=VALUE as for make
just flash examples/basic/hello-world nrf52840dk -B /tmp/b DEBUG_ADAPTER_ID=000683123456
dist/tools/flash/flash.py flash -C <app> BOARD=<board> [-B <dir>] [-j N] [-n] [--print-env] [--no-build] [VAR=VALUE…]
```

`-n` prints the flash commands (as `make -n` does), `--print-env` the
variables the flasher gets from the build system, `--no-build` flashes the
existing image (as `make -o all flash`). Build directory: as `just build`
(`<app>/bin/cmake-<board>`, or `-B`). Exit status: 0; 1 a failed command or
a missing flasher; 2 an error of the configuration (Make's `$(error)`); 3
the request is outside the data.

Scope: `examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on **nrf52840dk** (decision D22), with every
programmer the board supports.

Programmers of nrf52840dk
-------------------------

Found in the sources (base 5f5b94ff9c): `PROGRAMMERS_SUPPORTED` is
`openocd bmp` (boards/common/nrf52) plus `jlink` (cpu/cortexm_common). The
default is `jlink` if `$(JLINK)` (JLinkExe) is found by the shell, else
`openocd`. There is no `nrfjprog` programmer in RIOT (no
`makefiles/tools/nrfjprog.inc.mk`).

| PROGRAMMER | FLASHER | FFLAGS (FLASHFILE = ELFFILE) | variables the flasher's flash action reads (set for nrf52840dk) |
|---|---|---|---|
| jlink | `dist/tools/jlink/jlink.sh` | `flash $(FLASHFILE)` | JLINK=JLinkExe, JLINK_DEVICE=nrf52840_xxaa, JLINK_SERIAL (=DEBUG_ADAPTER_ID), JLINK_POST_FLASH (UICR reset pin), FLASH_ADDR=0x0, BINDIR, RIOTTOOLS; JLINK_IF/_RESET_FILE/_PRE_FLASH if set |
| openocd | `dist/tools/openocd/openocd.sh` | `flash $(FLASHFILE)` | OPENOCD_CONFIG (boards/common/nrf52/dist/openocd.cfg), OPENOCD_ADAPTER_INIT (J-Link adapter, `transport select swd`, `adapter serial` if DEBUG_ADAPTER_ID), OPENOCD_POST_INIT_CMDS (`nrf52_recover`), OPENOCD_PRE_VERIFY_CMDS (UICR); IMAGE_OFFSET, OPENOCD_SKIP_VERIFY, … if set |
| bmp | `dist/tools/bmp/bmp.py` | `$(BMP_OPTIONS) flash $(FLASHFILE)` | none (arguments only) |

`USE_PROGRAMMER_WRAPPER_SCRIPT=1` runs the flash command through
`dist/tools/programmer/programmer.py` (programmer.flash.yaml). Other
programmers of RIOT (pyocd, …) have no flash data: exit 3, flash with make.

Data model
----------

The programmer settings of a Make file are a rule list in YAML next to it,
the **single source**; the Make file includes the adapter generated from it
(`just generate-flash-data`, private recipe; `flash.py generate --check` in
the tests) as its first statement:

| Make file | flash data | adapter (generated) | content |
|---|---|---|---|
| `boards/nrf52840dk/Makefile.include` | `flash.yaml` | `flash.inc.mk` | JLINK_POST_FLASH, OPENOCD_PRE_VERIFY_CMDS |
| `boards/common/nrf52/Makefile.include` | `flash.yaml` | `flash.inc.mk` | PROGRAMMERS_SUPPORTED, JLINK, default PROGRAMMER, OpenOCD adapter, config, post-init |
| `cpu/nrf52/Makefile.include` | `flash.yaml` | `flash.inc.mk` | JLINK_DEVICE |
| `cpu/cortexm_common/Makefile.include` | `flash.yaml` | `flash.inc.mk` | PROGRAMMERS_SUPPORTED += jlink |
| `makefiles/tools/jlink.inc.mk` | `jlink.flash.yaml` | `jlink.flash.inc.mk` | FLASHER, FLASHFILE, FFLAGS, JLINK_* defaults, exports |
| `makefiles/tools/openocd.inc.mk` | `openocd.flash.yaml` | `openocd.flash.inc.mk` | FLASHER, FLASHFILE, FFLAGS, adapter include, OPENOCD_CONFIG fallback, exports |
| `makefiles/tools/openocd-adapters/jlink.inc.mk` | `jlink.flash.yaml` | `jlink.flash.inc.mk` | OPENOCD_ADAPTER_INIT, OPENOCD_TRANSPORT |
| `makefiles/tools/bmp.inc.mk` | `bmp.flash.yaml` | `bmp.flash.inc.mk` | FLASHER, FLASHFILE, FFLAGS |
| `makefiles/tools/programmer.inc.mk` | `programmer.flash.yaml` | `programmer.flash.inc.mk` | PROGRAMMER_FLASH (direct or wrapper) |
| `makefiles/vars.inc.mk` (generated whole from `vars.build.yaml`, step G0-3; its first rule is the include) | `vars.flash.yaml` | `vars.flash.inc.mk` | FLASH_ADDR ?= 0x0 |

What stays in these Make files is debugging, reset and terminal (later
steps). In `jlink.inc.mk`/`openocd.inc.mk` the include of `dbg_common.inc.mk`
(no flash data) stays first, so Make reads its files in the old order.
Root `build.yaml` no longer sets the stand-in `FLASHFILE ?= $(ELFFILE)` and
`makefiles/vars.build.yaml` no longer sets FLASH_ADDR: both come only from
the flash data; the build without Make does not read flash data (both are
empty there), Make and `flash.py` read them from the flash data
(`dist/tools/config_data/README.md`, build data and flash data).

Format: `{schema: 3, rules}` with the rule language of
`dist/tools/config_data/README.md` (schema 3) and two flash constructs
(validator and generator in `flashdata.py`; config_data is not changed):

| Construct | Meaning | Make (generated) |
|---|---|---|
| action `export: {targets, vars}` | the variables reach the flasher | `$(call target-export-variables,T,V…)` |
| condition `command: {var}` | the shell finds the command named by the variable | `ifneq (,$(shell command -v $(V)))` |

Algorithm, not data (`flash.py`, each part names the Make lines it
replaces): the order of reading (the flash data of an included Make file
before its build data; inside flash data only flash data; the programmer's
file after the CPU's, Makefile.include:376-377; programmer.inc.mk at :774),
the export rule of GNU Make 4.3 (a target-specific `export V ?=` exports a
defined V for every target, an undefined one only for the targets named, so
`flash` gets e.g. JLINK_SERIAL empty), the unsupported-programmer warning
(:392-403), the FLASHFILE check (:602-604), the recipe (`check_cmd` and
`PROGRAMMER_FLASH`, :711-717, :776-787, run with `/bin/sh -c` like Make)
and the flasher environment (exported variables of vars.build.yaml, command
line variables, exports).

Rule R3: what happens to Make's `flash`
---------------------------------------

`flash` stays in Make, as `all` in G3-1: every application, board and
programmer outside the data flashes with make; Make reads the generated
adapters, so both read the same programmer data. For the scope the entry
point is `just flash` (registered as target `flash` of step `g3-02-flash`,
hardware). A request outside the data stops with exit 3 (IOTLAB_NODE,
BUILD_IN_DOCKER, MOST_RECENT_PORT=1, riotboot, suit, FLASHDEPS, a programmer
without flash data, a board without data such as native64) instead of
falling back to make. `flash` leaves Make when the data covers every
board and programmer.

Parity (2026-11-21, base 5f5b94ff9c, golden files `tests/golden/`)
-----------------------------------------------------------------

Golden files (`tests/record_golden.py`, git archive of the base, GNU Make
4.3, `env -i PATH HOME LC_ALL=C`), per application and case: `make -n -o all
flash` (`-o all`: the build is the parity of G3-1), the environment of the
flasher (a recorder in place of the flasher script, the variables its flash
action reads, sample.FLASHER_READS) and the stub calls (the real flasher
script, stub JLinkExe/openocd/pipx on PATH: arguments and J-Link command
file). Header with command, commit, date; last line `## end`. Paths
normalised to @RIOTBASE@, @BINDIR@, @STUBS@; the flash command compared as
argument vector.

| nrf52840dk | hello-world | gnrc_networking | bindist |
|---|---|---|---|
| cases (default without/with JLinkExe, jlink, openocd, bmp; hello-world also serial number, wrapper, image offset, BMP_OPTIONS) | 10 | 5 | 5 |
| check_cmd line identical | 10/10 | 5/5 | 5/5 |
| flash command identical | 10/10 | 5/5 | 5/5 |
| flasher environment identical (26 variables) | 10/10 | 5/5 | 5/5 |
| stub calls identical | 10/10 | 5/5 | 5/5 |
| live Make with the adapters = golden (`-n` and stub calls) | 10/10 | 3/3 | 3/3 |

Board test (pending, needs the nRF52840 DK): `board_test` of the step in
`dist/tools/migration/steps.yaml`.

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/flash/tests -v
dist/tools/migration/run_tests.py --step g3-02-flash
```

46 tests in 5 modules (about 70 s, Make one at a time).

| Rule | Test classes | How |
|---|---|---|
| D1 validator | `test_data.ValidatorTest` | all 10 data files; 5 positive, 15 negative samples |
| D2 generator | `test_data.GeneratorTest` | exact Make text of `export`, `command`, `not command`, other rules |
| D3 names | `test_data.NamesTest` | Make file, data, adapter; flash data is no config/build data |
| D4 adapters up to date | `test_data.AdaptersTest` | `generate --check`; missing, hand-edited, stale, invalid on a copy |
| D5 single source | `test_data.OwnerTest` | the owner includes its adapter first, assigns no variable of its data (detector samples) |
| D6 scope | `test_data.ScopeTest` | the Make files Make reads for `flash` (jlink, openocd, bmp) assign no flash variable outside the adapters (documented exceptions: IOTLAB_NODE, riotboot) |
| A1-A6 algorithm | `test_algorithm.*` | export rule (with a live GNU Make sample), `command` probe, read order, exit 3 cases, Make's checks and messages, recipe prefixes, wrapper |
| P1-P5 parity | `test_parity.*` | table above; stub tools for the hardware |
| N1-N4 no Make | `test_no_make.*` | audit-hook trace for 3 applications x 3 programmers; `just flash` with stub make (never called), stub cmake/ninja, stub flasher tools; a failed build flashes nothing; static check; just recipe without make (detector samples) |
| R1, R3, O1 | `test_transition.*` | `just --dry-run flash`, parameters as `build`, Make keeps `flash`, register entry |

Also changed: `dist/tools/config_data/tests/test_parity.py` (the live
MAKEFILE_LIST comparison of G0-1 ignores the new `*flash.inc.mk` adapters),
the justfile (`flash`, `generate-flash-data`), the register.

Mutation probe
--------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| D1 | validator accepts export without variables | flash failures=1 |
| D2 | generator writes `command` negated | flash failures=2 |
| A1a | undefined variable exported for every target | flash failures=9 |
| A1b | defined variable exported only for literal flash | flash failures=37 |
| A2 | `command` probe always true | flash failures=11 |
| A3a | programmer data not read after the CPU | flash failures=56, errors=21 |
| A3b | flash data read after build data | flash failures=2 |
| A5a | no unsupported-programmer warning | flash failures=2 |
| A5b | FLASHFILE check removed | flash failures=1 |
| A6 | `@` not stripped | flash failures=53 |
| E1 | environment without the exports | flash failures=44 |
| X1 | cpu/nrf52/flash.yaml: JLINK_DEVICE without underscore | flash failures=22 |
| X2 | openocd.flash.yaml: OPENOCD_POST_INIT_CMDS not exported | flash failures=22 |
| X3 | nrf52 default programmer swapped | flash failures=24 |
| X4 | board data: other reset pin in JLINK_POST_FLASH | flash failures=22 |
| G1 | adapter edited by hand | flash failures=5 |
| G2 | owner without the include of its adapter | flash failures=13 |
| N1 | flash.py starts `make --version` | flash failures=11 |
| N2 | flash.py opens Makefile.include | flash failures=10 |
| R1 | just recipe calls make | flash failures=3, task_layer failures=1 |
| O1 | register: flash not hardware | flash failures=1 |

21/21 defects detected (2026-11-21; each file copied before the change,
restored from the copy and compared byte by byte; data mutations regenerate
the adapters, which are restored from their copies too).

Limits
------

* Scope: three applications on nrf52840dk, programmers jlink, openocd, bmp
  (OpenOCD with the J-Link adapter only). Other adapters, programmers and
  boards need their flash data.
* Not converted (exit 3): IoT-LAB, Docker, MOST_RECENT_PORT (serial number
  from the TTY), riotboot/SUIT images, FLASHDEPS/preflash, `flash-recipe`
  overrides of other boards.
* The check line of the recipe is Make's text without colour (COLOR_ECHO of
  a non-terminal).
* The flasher itself is not run on hardware here (board test pending); the
  firmware image comes from `just build`, whose firmware parity needs the
  toolchain (G3-1, P5).
