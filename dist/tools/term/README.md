Terminal without Make: terminal and debugger data (migration step G2B-1)
======================================================================

`just term <application> <board>` does what GNU Make's target `term` does:
it runs the terminal program of `RIOT_TERMINAL` with the port, the flags and
the environment Make gives it; `just cleanterm` does what `make cleanterm`
does (pyterm without its logging and prefixes). Nothing is built. Inputs are
**data only**: the YAML data of the repository (resolver G0-2, build data
G3-1, flash data G3-2) and the terminal and debugger data of this step, plus
the variables of the environment as Make takes them. No make process is
started, no Make file is opened, no Make syntax is parsed.

```sh
just term examples/basic/hello-world nrf52840dk                          # pyterm on /dev/ttyACM0
just term examples/basic/hello-world nrf52840dk RIOT_TERMINAL=picocom    # VAR=VALUE as for make
just term examples/basic/hello-world nrf52840dk MOST_RECENT_PORT=1       # the TTY of the board
PORT=/dev/ttyUSB0 just term examples/basic/hello-world nrf52840dk        # environment, as for make
just cleanterm examples/basic/hello-world nrf52840dk
dist/tools/term/term.py term|cleanterm -C <app> BOARD=<board> [-n] [--print-env] [VAR=VALUE…]
```

`-n` prints the commands (as `make -n`), `--print-env` the variables the
terminal gets from the build system. Exit status (as Make): 0; 2 the
terminal program is missing (Make's message `Terminal program X is required
but not found in PATH.  Aborting.`) or fails, or an error of the
configuration (Make's `$(error)`); 3 the request is outside the data. Ctrl+C
ends the terminal and then this program by SIGINT, as Make.

Scope: `examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on **nrf52840dk**, with every terminal Make
offers for the board (decision E1, 2026-11-22).

Terminals of nrf52840dk
-----------------------

| RIOT_TERMINAL | program (TERMPROG) | flags (TERMFLAGS), TERMENV |
|---|---|---|
| pyterm (default) | `dist/tools/pyterm/pyterm` | `-p "$(PORT)" -b "$(BAUD)" -ln "/tmp/pyterm-$(USER)" -rn "<date>-<app>-<board>" $(PYTERMFLAGS)` |
| picocom | `picocom` | `--nolock --imap lfcrlf --baud "$(BAUD)" "$(PORT)"` |
| socat | `socat` | Linux: `- open:$(PORT),b$(BAUD),…`; macOS: `…,ispeed=…,ospeed=…` |
| miniterm | the first of `pyserial-miniterm.py`, `pyserial-miniterm`, `miniterm.py`, `miniterm` on PATH; none: Make's `$(error)` (exit 2) | `--eol LF "$(PORT)" "$(BAUD)" $(MINITERMFLAGS)` |
| jelly | `Jelly` | `$(PORT)` |
| jlink | `dist/tools/jlink/jlink.sh` | `term-rtt` |
| openocd-rtt | `dist/tools/openocd/openocd.sh` | `term-rtt`; `RAM_START_ADDR=… RAM_LEN=…` |
| semihosting | DEBUGGER of the programmer (`openocd.sh`, `jlink.sh`, `bmp.py`) | DEBUGGER_FLAGS (`debug <ELF>`); OPENOCD_DBG_EXTRA_CMD `-c 'arm semihosting enable'` exported |
| native | the ELF file (Make's BINDIR `<app>/bin/<board>`, or `BINDIR=…`) | |
| bootterm | `dist/tools/bootterm/bt`, which Make builds first (TERMDEPS) | **exit 3**: needs a build (E1) |

`stdio_rtt` selects openocd-rtt (PROGRAMMER=openocd) or jlink
(PROGRAMMER=jlink), else Make's warning. Port (E2): `PORT` from the command
line or the environment; else `MOST_RECENT_PORT=1` asks
`dist/tools/usb-serial/ttys.py` exactly as Make (filter `--model J-Link` of
the board; the serial number becomes DEBUG_ADAPTER_ID); else by OS (`uname`,
as Makefile.include:130-131: the resolver takes it from the same system
call): Linux `PORT_LINUX` (`/dev/ttyACM0`, with PROGRAMMER=bmp
`/dev/ttyACM1`), macOS `PORT_DARWIN` (first `/dev/tty.usbmodem*`, bmp the
second). `TERMLOG=<file>` (or `TERMTEE`) appends `| tee -a <file>`.

Data model
----------

The terminal settings (`term`) and the debugger settings the terminal needs
(`debug`: DEBUGGER for semihosting, GDB, DBG_EXTRA_FLAGS, reused by the
later step of `debug`, decision 1b) of a Make file are rule lists in YAML
next to it, the **single source**; the Make file includes the adapter
generated from it (`just generate-term-data`, private recipe; `term.py
generate --check` in the tests), after its flash adapter:

| Make file | data | adapter (generated) | content |
|---|---|---|---|
| `makefiles/tools/serial.inc.mk` (now only the include) | `serial.term.yaml` | `serial.term.inc.mk` | MOST_RECENT_PORT, PORT_LINUX/PORT_DARWIN, PORT, PROG_DEV, BAUD, stdio_rtt, RIOT_TERMINAL and TERMPROG/TERMFLAGS/TERMENV of every terminal |
| `boards/common/nrf52/Makefile.include` | `term.yaml` | `term.inc.mk` | ports of the Black Magic Probe |
| `boards/nrf52840dk/Makefile.include` | `term.yaml` | `term.inc.mk` | TTY_BOARD_FILTER, DEBUG_ADAPTER_ID_IS_TTY_SERIAL |
| `makefiles/tools/jlink.inc.mk` | `jlink.debug.yaml` | `jlink.debug.inc.mk` | DEBUGGER, DEBUGSERVER, RESET and flags, export of DBG_EXTRA_FLAGS |
| `makefiles/tools/openocd.inc.mk` | `openocd.debug.yaml` | `openocd.debug.inc.mk` | DEBUGGER, DEBUGSERVER, DEBUGCLIENT, RESET and flags, exports |
| `makefiles/tools/bmp.inc.mk` | `bmp.debug.yaml` | `bmp.debug.inc.mk` | DEBUGGER, RESET and flags |
| `makefiles/tools/dbg_common.inc.mk` (now only the include) | `dbg_common.debug.yaml` | `dbg_common.debug.inc.mk` | USE_PYCORTEXMDEBUG, DEBUGDEPS, DBG_EXTRA_FLAGS |
| `makefiles/tools/gdb.inc.mk` (now only the include) | `gdb.debug.yaml` | `gdb.debug.inc.mk` | GDBPREFIX, GDB (exported) |
| `makefiles/toolchain/gnu.inc.mk` | `gnu.debug.yaml` | `gnu.debug.inc.mk` | the include of gdb.inc.mk (where it was, after the build part) |
| `Makefile.include` | `debug.yaml` | `debug.inc.mk` | DEBUG_ELFFILE (included where the line was, after riotboot.mk) |

The test data of step G2B-3 (kind `test`: `tests.test.yaml`, `test.yaml`,
`setup_dirs.test.yaml`) use the same format and generator; they are listed
in `dist/tools/test/README.md`.

`jlink.inc.mk` and `openocd.inc.mk` still include `dbg_common.inc.mk` first,
so Make reads its files in the old order; their debugger data names that
include as a `stand_in` rule (schema 4, step G0-3): read by `term.py`, left
out of the adapter.

Format: `{schema: 4, rules}` with the rule language of the flash data
(`dist/tools/flash/flashdata.py`; validator and generator reused) without
`section`, plus three constructs (decision 1, option A):

| Construct | Meaning | Make (generated) |
|---|---|---|
| condition `command: {name}` | the shell finds the command NAME | `ifneq (,$(shell command -v NAME 2>/dev/null))` |
| value `{word: {var, index}}` | word `index` of var (1 first, -1 last) | `$(firstword $(V))`, `$(lastword $(V))`, `$(word N,$(V))` |
| `set: {…, export: true}` (schema 4) | exported to every command | `export V ?= …` |

The answers of the shell are probes, as the toolchain probes of G0-3
(`makefiles/build_providers.inc.mk`): the data reads `PROBE_TTY_DETECTED`
(`$(TTY_SELECT_CMD) || echo 'no-tty-detected no-serial-detected'`),
`PROBE_DATE_TIME` (`date +%Y-%m-%d_%H.%M.%S`, E8), `PROBE_TTY_USBMODEM`
(sorted `/dev/tty.usbmodem*`) and `PROBE_GDB_STATUS` (`$(GDBPREFIX)gdb -v`);
for Make they are defined in `makefiles/term_providers.inc.mk` with the old
commands (recursive: each runs when the data reads it), `term.py` computes
them in Python with the same shell.

Algorithm, not data (`term.py`, each part names the Make lines of the base
it replaces): Make's variables of the environment (origin environment:
`?=` keeps them, `=` replaces them, the command line wins; passed on with
Make's value), the probes, the order of reading (flash, debugger, terminal
data of a Make file before its build data; the programmer's flash and
debugger data after the CPU's Make file, Makefile.include:312; the terminal
data of serial.inc.mk after it, :316; DEBUG_ELFFILE, :454), the scope checks,
TERMTEE (:659-661), `cleanterm`'s `export PYTERMFLAGS +=` (:673), the recipe
(check_cmd :565-572 with the colours of `makefiles/color.inc.mk`, and
`${TERMENV} $(TERMPROG) $(TERMFLAGS) $(TERMTEE)`, :667-669; run with
`/bin/sh -c` like Make, stop at the first failing line with exit 2), the
environment of the terminal (exported variables of vars.build.yaml, command
line and environment variables, target-export-variables with the GNU Make 4.3
rule of flash.py), signals (SIGINT, SIGHUP, SIGQUIT, SIGTERM: wait for the
terminal, SIGTERM passed on, then end by the signal).

Rule R3: what happens to Make's `term` and `cleanterm`
------------------------------------------------------

Both stay in Make (E4), as `flash` in G3-2: every application, board and
terminal outside the data opens with make; Make reads the generated adapters
and probes, so both read the same data. For the scope the entry points are
`just term` and `just cleanterm` (step `g2b-01-term`, hardware). A request
outside the data stops with exit 3 instead of falling back to make:
bootterm (TERMDEPS), EMULATE=1, IOTLAB_NODE, riotboot, suit, a programmer
without flash or debugger data (e.g. pyocd), a board without terminal data
(e.g. native64). The test runner (`dist/pythonlibs/testrunner/spawn.py`)
still runs `make term` (step G2B-3).

Deviations from Make (decided 2026-11-22)
-----------------------------------------

* **E3** No combined flash and terminal: `make flash term` is two calls,
  `just flash <app> <board> && just term <app> <board>`. `just flash` builds
  into `<app>/bin/cmake-<board>`; `just term` uses Make's BINDIR
  `<app>/bin/<board>` for the ELF of `native`/`semihosting` unless
  `BINDIR=<app>/bin/cmake-<board>` is given (as for make).
* **E6** On an error the message of the recipe or of the data is printed
  (`error: <data file>: <text>` for Make's `$(error)`), without Make's
  `make: *** [...] Error N` or `*** … Stop.` line; exit status as Make (2).
* **E1** `RIOT_TERMINAL=bootterm` exits 3 (Make first builds `bt`).
* **Decision 2** `EMULATE=1` exits 3; Make fails as well (exit 2: no rule for
  `boards/nrf52840dk/dist/board.resc`) and creates an empty
  `$TMPDIR/riot_<app>_<board>.XXXXX` with mktemp on every call, which
  `term.py` does not.
* Warnings are printed as `warning: <text>` (Make: `<file>:<line>: <text>`).
* **E9** The callers (`examples/networking/gnrc/networking/README.md`,
  `dist/tools/usb-serial/README.md`, the board test text of step
  `g3-02-flash`) still say `make term`: switching them (R4) is deferred.

Parity (2026-11-22, base 481caa4b65, golden files `tests/golden/`)
-----------------------------------------------------------------

Golden files (`tests/record_golden.py`, git archive of the base, GNU Make
4.3, `env -i PATH HOME LC_ALL=C USER TMPDIR`), per application and case:
`make -n term` (or `cleanterm`) and `make term` with a recorder in place of
the terminal (scripts of dist/tools replaced in the archive, picocom, socat,
Jelly, miniterm on PATH, the image for native): the echoed command, the
arguments, the 38 variables the terminals read (`sample.TERM_READS`) and the
calls of ttys.py. Stubs: `date` (E8), `python3` for ttys.py (a TTY found or
none); USER fixed. Header with command, commit, date; last line `## end`.

| nrf52840dk | hello-world | gnrc_networking | bindist |
|---|---|---|---|
| cases (11 terminals, port cases, cleanterm, errors) | 31 | 20 | 20 |
| `make -n` lines identical (error: same message, exit 2) | 31/31 | 20/20 | 20/20 |
| terminal call identical (arguments, 38 variables, ttys.py calls) | 31/31 | 20/20 | 20/20 |
| echoed command line and exit status identical | 31/31 | 20/20 | 20/20 |
| live Make with the adapters = golden (`-n`) | 31/31 | 20/20 | 20/20 |
| live Make with the adapters = golden (terminal call, PATH terminals and image) | 9/9 | 6/6 | 6/6 |

For the terminals that are scripts of dist/tools (pyterm, jlink.sh,
openocd.sh, bmp.py) the terminal call of `term.py` is compared as the
command of `-n` with the environment of `--print-env` (the work tree keeps
the scripts); the others run.

Board test (pending, needs the nRF52840 DK): `board_test` of the step in
`dist/tools/migration/steps.yaml`.

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/term/tests -v
dist/tools/migration/run_tests.py --step g2b-01-term
```

60 tests in 6 modules (about 2.5 min, Make one at a time).

| Rule | Test classes | How |
|---|---|---|
| D1 validator | `test_data.ValidatorTest` | all 10 data files; 9 positive, 18 negative samples |
| D2 generator | `test_data.GeneratorTest` | exact Make text of the three constructs, flash and configuration rules, `stand_in` left out |
| D3 names | `test_data.NamesTest` | Make file, data, adapter for both kinds; no config, build or flash data |
| D4 adapters up to date | `test_data.AdaptersTest` | `generate --check`; missing, hand-edited, stale, invalid on a copy |
| D5 single source | `test_data.OwnerTest` | the owner includes its adapter (after the flash adapter and the documented leading includes) and assigns no variable of its data; `stand_in` names the owner (detector samples) |
| D6 scope | `test_data.ScopeTest` | the Make files Make reads for `term` (4 terminal/programmer pairs) assign no terminal or debugger variable outside the adapters (documented exceptions) |
| A1-A8 algorithm | `test_algorithm.*` | word, `command: {name}`, probes, environment, read order, exit 3 cases (no mktemp directory left), recipe and colours, TERMTEE, cleanterm, the terminal data alone (stdio_rtt, miniterm order, ports) |
| P1-P5 parity | `test_parity.*` | table above |
| I1-I5 interactive (E7) | `test_interactive.*` | stub terminal, each scenario with term.py and live Make: stdin through a pipe, pty (isatty), Ctrl+C to the process group (ends by SIGINT, no terminal left; also through `just term`), SIGTERM, exit status 0/2 |
| N1-N4 no Make | `test_no_make.*` | audit-hook trace for 3 applications x 5 runs; `just term`/`just cleanterm` with a stub make (never called); static check; just recipes without make (detector samples) |
| R1, R3, O1 | `test_transition.*` | `just --dry-run`, parameters as `flash`, Make keeps `term`/`cleanterm`, live Make with the adapters = golden, register entry |

Also changed: `dist/tools/config_data/tests/test_parity.py` (the live
MAKEFILE_LIST comparison of G0-1 ignores the new adapters and
`term_providers.inc.mk`), the justfile (`term`, `cleanterm`,
`generate-term-data`), the register.

Mutation probe
--------------

| Part | Deliberate defect | Failing tests |
|---|---|---|
| D1 | validator accepts word index 0 | term failures=1 |
| D2 | generator writes `command: {name}` negated | term failures=2 |
| D4 | generate --check never reports | term failures=1 |
| D5 | serial.inc.mk without the include of its adapter | term failures=96, errors=2 |
| G1 | adapter edited by hand | term failures=44 |
| A1 | lastword gives the first word | term failures=5 |
| A2 | `command: {name}` always true | term failures=5 |
| A3a | $(shell) keeps newlines | term failures=2 |
| A3b | date probe without seconds | term failures=1 |
| A4 | environment not imported | term failures=32 |
| A5a | serial data read before the programmer | term failures=3 |
| A5b | debugger data not read | term failures=69 |
| A6a | EMULATE=1 not rejected | term failures=1 |
| A6b | TERMDEPS not rejected (bootterm) | term failures=1 |
| A6c | board without terminal data accepted | term failures=1 |
| A6d | unknown programmer: no FLASHFILE error (`Makefile.include:470-472`, exit 2; added with G2B-2 debug, 2026-11-22) | term failures=2 |
| A7a | colour test ignores stderr | term failures=1 |
| A7b | cleanterm without PYTERMFLAGS | term failures=5 |
| A7c | TERMENV also for cleanterm | term failures=1 |
| A7d | no TERMTEE from TERMLOG | term failures=1 |
| E1 | terminal environment without target exports | term failures=65 |
| S1 | Ctrl+C: exit 130 instead of the signal | term failures=2 |
| S2 | failing terminal: exit 1 | term failures=3 |
| X1 | serial.term.yaml: PORT_LINUX ttyACM2 | term failures=71 |
| X2 | nrf52 term.yaml: bmp port ttyACM0 | term failures=6 |
| X3 | nrf52840dk term.yaml: other TTY filter | term failures=12 |
| X4 | gdb.debug.yaml: other default GDB | term failures=89 |
| X5 | openocd.debug.yaml: DEBUGGER_FLAGS without the ELF | term failures=6 |
| N1 | term.py starts `make --version` | term failures=18 |
| N2 | term.py opens Makefile.include | term failures=17 |
| R1 | just recipe calls make | term failures=3 |
| O1 | register: term not hardware | term failures=1 |

31/31 defects detected (2026-11-22; each file copied before the change, restored from the copy and compared by SHA-256; data mutations regenerate the adapters, which are restored from their copies too; HOME a temporary directory). The first run found one gap: a `date` probe with another format went unnoticed outside the parity tests; `test_algorithm.ProbeTest.test_date_format` closes it.

Limits
------

* Scope: three applications on nrf52840dk. Other boards (they may set the
  terminal in Make, e.g. native64) need their terminal data first.
* The terminals are run with stubs here; the board test is pending.
* macOS: the Darwin branches (socat flags, `/dev/tty.usbmodem*`, `echo -e`
  and `SHELL=bash` of the colours) are data and tested with `OS=Darwin` and
  fakes on Linux only.
* SIGTERM to `term.py` alone (not to the process group) leaves the terminal
  running, as with Make (both pass it only to the shell of the line).
