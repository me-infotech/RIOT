Debugger without Make (migration step G2B-2)
============================================

`just debug <application> <board>` does what GNU Make's target `debug` does:
it runs DEBUGGER of the programmer (`dist/tools/openocd/openocd.sh`,
`dist/tools/jlink/jlink.sh`, `dist/tools/bmp/bmp.py`) with DEBUGGER_FLAGS and
the environment Make gives it; `just debug-server` and `just debug-client` do
what `make debug-server` and `make debug-client` do (DEBUGSERVER,
DEBUGCLIENT). Nothing is built: the image must exist. Inputs are **data
only**: the YAML data of the repository (resolver G0-2, build data G3-1,
flash data G3-2, terminal and debugger data G2B-1, the setsid rule of macOS
of this step) plus the variables of the environment as Make takes them. No
make process is started, no Make file is opened, no Make syntax is parsed.

```sh
just flash examples/basic/hello-world nrf52840dk && \
  just debug examples/basic/hello-world nrf52840dk BINDIR=examples/basic/hello-world/bin/cmake-nrf52840dk
just debug examples/basic/hello-world nrf52840dk PROGRAMMER=jlink      # VAR=VALUE as for make
just debug examples/basic/hello-world nrf52840dk MOST_RECENT_PORT=1    # the adapter of the board
just debug-server examples/basic/hello-world nrf52840dk                # terminal 1
just debug-client examples/basic/hello-world nrf52840dk                # terminal 2
dist/tools/debug/debug.py debug|debug-server|debug-client -C <app> BOARD=<board> [-n] [--print-env] [VAR=VALUE…]
```

`-n` prints the commands (as `make -n`), `--print-env` the variables the
debugger gets from the build system. Exit status (as Make, D7): 0 when the
script ends with 0 (`openocd.sh debug` always does); 2 the program is not
set (Make's hint), missing (`Debug program X is required but not found in
PATH.  Aborting.`) or fails, or a configuration error (Make's `$(error)`,
e.g. `FLASHFILE is not defined for this board` for an unknown programmer);
3 the request is outside the data. Ctrl+C: as with Make the debugger's
process group gets it; `debug.py` waits for the script and then ends by
SIGINT.

Scope: `examples/basic/hello-world`, `examples/networking/gnrc/networking`,
`examples/advanced/bindist` on **nrf52840dk** with the programmers openocd,
jlink and bmp (D2, 1:1 as Make); the default programmer as Make (jlink when
`JLinkExe` is found, else openocd: the flash data of the board).

| PROGRAMMER | debug | debug-server | debug-client |
|---|---|---|---|
| openocd | `openocd.sh debug <ELF>` (openocd under setsid, then GDB; the script kills openocd and removes its pid file at the end) | `openocd.sh debug-server` (until EOF on stdin, Ctrl+D) | `openocd.sh debug-client <ELF>` |
| jlink | `jlink.sh debug <ELF>` (JLinkGDBServer under setsid, then GDB) | `jlink.sh debug-server` | Make's hint `$(DEBUGCLIENT) is not set…`, exit 2 |
| bmp | `bmp.py debug <ELF>` (`#!/usr/bin/env -S pipx run`) | Make's hint, exit 2 | Make's hint, exit 2 |

The ELF file (D5) is Make's `DEBUG_ELFFILE` = `$(BINDIR)/<app>.elf` with
BINDIR `<app>/bin/<board>`; `just flash` builds into `<app>/bin/cmake-<board>`,
so pass `BINDIR=…` for that image. `MOST_RECENT_PORT=1` (D9) asks
`dist/tools/usb-serial/ttys.py` through term's serial data; its serial
number becomes DEBUG_ADAPTER_ID and so JLINK_SERIAL (jlink) as in Make.

Data and algorithm
------------------

The debugger data are those of step G2B-1 (`dist/tools/term/README.md`:
`openocd.debug.yaml`, `jlink.debug.yaml`, `bmp.debug.yaml`,
`dbg_common.debug.yaml`, `gdb.debug.yaml`, `debug.yaml`). This step adds the
rule of Makefile.include:577-586 (base 481caa4b65: 575-584) to `debug.yaml`
(D4, the single source; Make reads it in the generated `debug.inc.mk`, which
Makefile.include includes at :457, where DEBUG_ELFFILE was; nothing between
the two places reads OS, MAKECMDGOALS, SETSID or DEBUGDEPS). Two
constructs (schema 4, `dist/tools/term/termdata.py`, decided 2026-11-22):

| Construct | Meaning | Make (generated) |
|---|---|---|
| condition `goal: TARGET` | TARGET is a goal of the call | `ifneq (,$(filter TARGET,$(MAKECMDGOALS)))` |
| a word `${NAME}` in `export.vars` (P1, option A) | the variable named by NAME's value | `$(call target-export-variables,T,$(NAME))` |

The `setsid` test uses the existing `command: {name: setsid}` (P2). Make's
rule exports `$(SETSID)`, i.e. a variable named after the **path** of the
setsid binary, not `SETSID`: the scripts therefore never see the setsid that
Make builds (`: ${SETSID:=setsid}` in openocd.sh and jlink.sh). This is
Make's behaviour since 5b265088fe and is kept as it is (P1, option A).

Algorithm, not data (`debug.py`, with term.py's evaluation): the scope checks
(term's, plus DEBUGDEPS and a programmer without debugger data), the
`$(error)` of an empty FLASHFILE (Makefile.include:470-472), the three rules
(Makefile.include:684-720: check_cmd with Make's colours, the hint when the
program is not set followed by `false`), the environment (term's: exported
variables, command line, environment, target exports) and running (term's:
`/bin/sh -c` per line, exit 2 at the first failure, signals). term.py got
two changes for this step: the goal and `${NAME}` export of the evaluator,
and target exports with patterns (`OPENOCD_TARGETS = debug% flash% reset`:
`%` stands for a non-empty stem as for Make's pattern-specific variables, so
debug-server and debug-client get GDB_PORT_CORE_OFFSET and the other
openocd variables, debug not).

Rule R3: what happens to Make's targets
---------------------------------------

All three stay in Make (D6): everything outside the data opens with make,
which reads the generated adapters. A request outside the data stops with
exit 3: DEBUGDEPS non-empty (USE_PYCORTEXMDEBUG=1, which Make fetches from
GitHub; EMULATE=1; macOS without setsid, which Make builds), a programmer
without debugger data (pyocd and every other one), a board without terminal
data (native64), IOTLAB_NODE, riotboot, suit. The callers (READMEs, guides)
still say `make debug` (D10, R4 deferred).

Deviations from Make and limits (decided 2026-11-22)
----------------------------------------------------

* **D5** No combined `make flash debug`: two calls.
* **D7** On an error the message is printed without Make's `make: ***`
  line; `warning:`/`error:` instead of Make's `<file>:<line>:`.
* **D3** DEBUGDEPS: exit 3 instead of building or fetching; for EMULATE=1
  Make fails as well (no rule for `boards/nrf52840dk/dist/board.resc`) and
  leaves a mktemp directory, debug.py does not.
* **D11** `debug-client` is missing in Make's `.PHONY`: with a file named
  `debug-client` in the application directory Make reports it up to date
  and runs nothing; not imitated. `debugr` has no Make rule and is not
  offered.
* **D7** jlink: after Ctrl+C in GDB and `quit`, JLinkGDBServer keeps running
  (also without Ctrl+C: jlink.sh kills only its setsid shell), as with Make.
* SIGTERM to `debug.py` alone is passed to the shell of the line, as Make.
* The scripts run with stubs here; the board test is pending
  (`board_test` of the step in `dist/tools/migration/steps.yaml`; bmp is not
  applicable without a probe). macOS is tested with `OS=Darwin` and a PATH
  without setsid on Linux only.

Parity (2026-11-22, golden files from d04191b950 = G2B-1, `tests/golden/`)
-------------------------------------------------------------------------

Golden files (`tests/record_golden.py`, git archive of the base unchanged,
GNU Make 4.3, `env -i PATH HOME LC_ALL=C USER TMPDIR G2B_*`): per case
`make -n <goal>` and `make <goal>` with the real scripts and stub tools on
PATH (`tests/debug_sample.py`): the output, the exit status, each stub call
with its arguments and 42 variables (DEBUG_READS), the calls of ttys.py, the
servers left running. stdin is a pipe closed once the server started.

| nrf52840dk | hello-world | gnrc_networking | bindist |
|---|---|---|---|
| cases (3 programmers x 3 targets; hello-world also default programmer x2, environment, OPENOCD_DBG_EXTRA_CMD, MOST_RECENT_PORT x2, gdb-multiarch, macOS x2, errors x5, outside x5) | 28 | 9 | 9 |
| `make -n` lines identical (error: same message, exit 2) | 23/23 | 9/9 | 9/9 |
| run identical (output, exit status, stub calls with environment, servers left) | 22/22 | 9/9 | 9/9 |
| outside the data: debug.py exit 3 (Make: builds, fetches or fails) | 5/5 | - | - |
| live Make with the adapters = golden (`-n` and run) | 27/27 | 9/9 | 9/9 |

PyCortexMDebug (USE_PYCORTEXMDEBUG=1) is not recorded: Make would fetch it.

Rules and tests
---------------

```sh
python3 -m unittest discover -s dist/tools/debug/tests -v
dist/tools/migration/run_tests.py --step g2b-02-debug
```

| Rule | Test classes | How |
|---|---|---|
| D1 validator | `test_data.ValidatorTest` | 4 positive, 9 negative samples of `goal` and `${NAME}` |
| D2 generator | `test_data.GeneratorTest` | exact Make text, negated goal |
| D3 single source | `test_data.SingleSourceTest` | no SETSID in Makefile.include, include once, adapter = Make's statements, up to date |
| D4 evaluation | `test_data.EvaluationTest` | DEBUGDEPS and export only for Darwin + debug + no setsid |
| D5 programmer data | `test_data.ProgrammerDataTest` | openocd, jlink, bmp have DEBUGGER; no pyocd data |
| A1 recipe | `test_algorithm.RecipeTest` | check_cmd per goal, colours (Linux, macOS), hint text as the shell prints it |
| A2 exit 3 | `test_algorithm.OutsideTest` | PyCortexMDebug, EMULATE, macOS, pyocd, a flash-only programmer, native64; nothing fetched, built or left in TMPDIR |
| A3 exit 2 | `test_algorithm.ErrorTest` | FLASHFILE error, missing debugger, hint; no `make: ***` |
| A4 target exports | `test_algorithm.ExportTest` | `debug%` matches debug-server/-client, not debug |
| A5 environment | `test_algorithm.EnvironmentTest` | PROGRAMMER from the environment, command line wins |
| P1-P4 parity | `test_parity.*` | table above |
| I1-I4 interactive (D7) | `test_interactive.*` | with debug.py and live Make in a process group: Ctrl+C then `quit` (openocd killed, pid file removed, end by SIGINT; also through `just debug`), jlink server orphaned as Make, debug-server until EOF, SIGTERM |
| N1-N4 no Make | `test_no_make.*` | audit-hook trace (3 applications x 4 runs), `just debug*` with a stub make, static check, recipes without make (term's detectors) |
| R1, R3, O1 | `test_transition.*` | `just --dry-run`, parameters as `flash`, Make keeps the three rules (and `.PHONY` without debug-client), live Make = golden, register entry |

Also changed: `dist/tools/term/term.py` (goal, `${NAME}` export, pattern
targets, parameters of `evaluate`), `dist/tools/term/termdata.py` (the two
constructs), `dist/tools/term/tests/test_data.py` (Makefile.include keeps
`DEBUGDEPS += $(EMULATORDEPS)`, now an allowed line for the owner test),
`debug.yaml`, `debug.inc.mk`, `Makefile.include`, the justfile (`debug`,
`debug-server`, `debug-client`), the register.

Mutation probe
--------------

| Part | Deliberate defect | First failing module (fast to slow) |
|---|---|---|
| D1a | validator accepts a goal with a blank | test_data: FAILED (failures=1) |
| D1b | validator rejects ${NAME} in export.vars | test_data: FAILED (failures=3, errors=5) |
| D2a | generator writes the goal condition negated | test_data: FAILED (failures=2) |
| D2b | generator writes ${NAME} of vars literally | test_data: FAILED (failures=2) |
| D3 | Makefile.include keeps a SETSID line | test_data: FAILED (failures=1) |
| G1 | debug.inc.mk edited by hand | test_data: FAILED (failures=1) |
| A1 | goal condition always true | test_data: FAILED (failures=2) |
| A2 | ${NAME} of export.vars not expanded | test_data: FAILED (failures=1) |
| A3 | DEBUGDEPS not rejected | test_algorithm: FAILED (failures=2) |
| A4 | programmer without debugger data accepted | test_algorithm: FAILED (failures=1) |
| A5 | FLASHFILE error left out | test_algorithm: FAILED (failures=1) |
| A6 | check_cmd description of debug-server wrong | test_algorithm: FAILED (failures=1) |
| A7 | hint without `false` | test_algorithm: FAILED (failures=4) |
| A8 | pattern target matches an empty stem | test_algorithm: FAILED (failures=2) |
| A9 | board without terminal data accepted | test_parity: FAILED (failures=1) |
| E1 | environment not imported | test_algorithm: FAILED (failures=1) |
| S1 | Ctrl+C: exit 130 instead of the signal | test_interactive: FAILED (failures=3) |
| S2 | failing debugger: exit 1 | test_algorithm: FAILED (failures=1) |
| N1 | debug.py starts make | test_no_make: FAILED (failures=16) |
| N2 | debug.py opens Makefile.include | test_no_make: FAILED (failures=15) |
| R1 | just recipe debug calls make | test_no_make: FAILED (failures=1) |
| O1 | register: debug-client not hardware | test_transition: FAILED (failures=1) |
| X1 | openocd.debug.yaml: DEBUGCLIENT_FLAGS without the ELF | test_no_make: FAILED (failures=4) |
| X2 | debug.yaml: the setsid rule for debug-server | test_data: FAILED (failures=3) |

24/24 defects detected (2026-11-22; each file copied before the change, restored from the copy and compared by SHA-256; data mutations regenerate the adapters, which are restored from their copies too; HOME a temporary directory). The modules run from fast to slow (`test_data`, `test_algorithm`, `test_no_make`, `test_interactive`, `test_transition`, `test_parity`) and stop at the first that fails; the count is that module's.
