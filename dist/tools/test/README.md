# Tests of an application without Make (step G2B-3)

`just test` runs the test scripts of an application, as `make test` did;
`just test-available` says whether there are any, as `make test/available`
did. Both read data only (`test.py`); nothing is built or flashed (flash
first with `just flash`). The rules stay in Make for the applications and
boards outside the data (R3).

```sh
just flash examples/basic/hello-world nrf52840dk
just test examples/basic/hello-world nrf52840dk TESTS="/path/01-run.py /path/02-run.py"
just test-available examples/basic/hello-world nrf52840dk     # exit 2: no tests
dist/tools/test/test.py test -n -C examples/basic/hello-world BOARD=nrf52840dk
dist/tools/test/test.py test --print-env -C examples/basic/hello-world BOARD=nrf52840dk
```

Each argument after the board is one `VAR=VALUE` (`[positional-arguments]`),
so `TESTS` can name several scripts as on Make's command line. The recipe of
`test/available` is named `test-available` (just recipe names cannot hold
`/`). The three applications of the scope have no test scripts (decision
T1): `just test` runs the empty loop and exits 0, as Make does; the scripts
are given with `TESTS=` (Make reads TESTS with `?=`).

## What it does

As `make -C <app> test` (`makefiles/tests/tests.inc.mk`, base
`db4fc1c576`):

- **scripts:** TESTS, by default the regular executable files of
  `$(APPDIR)/tests` whose name does not end with `~`; each runs in the
  application directory as `$(TEST_EXECUTOR) $(TEST_EXECUTOR_FLAGS) <script>`
  in Make's loop; the first failure ends the run (exit 2).
- **environment of the scripts:** Make's export set as far as the data hold
  it (the exported build variables, the command line, the environment,
  `TESTRUNNER_RESET_AFTER_TERM` exported for `test` (empty when unset, as
  GNU Make 4.3), PYTHONPATH with `dist/pythonlibs`), and what GNU Make adds:
  `MAKEFLAGS` (`rw --no-print-directory -- <command line, reversed, quoted>
  <directory variables>`), `MFLAGS`, `MAKELEVEL`, `MAKE_TERMOUT`/`MAKE_TERMERR`
  on a terminal. The inner `make cleanterm` of `spawn.py` thus sees the
  command line variables, as under Make (decision T3).
- **test-available:** Make's messages (`Board … not in TEST_ON_CI_WHITELIST`,
  `Board … is in TEST_ON_CI_BLACKLIST`) and `test -n "$(TESTS)"`. The
  whitelist is read when Make reads the rule, i.e. before
  `makefiles/murdock.inc.mk` sets `TEST_ON_CI_WHITELIST ?= all`: unset, it
  is not checked; `TEST_ON_CI_WHITELIST=all` fails, as in Make.
- **exit status:** 0; 2 a script or check fails, or a configuration error
  (Make's `$(error)`, e.g. an unknown programmer), without Make's `make: ***`
  line; 3 outside the data: `test` that Make runs in Docker (T6, see
  below), TEST_DEPS (the
  terminal's TERMDEPS, e.g. bootterm), EMULATE=1, IOTLAB_NODE, a board or
  programmer without data, an application without data, MAKEFLAGS or MFLAGS
  in the environment (a call from inside make, which would merge them). A
  script ended by a signal ends test.py by the same signal (term.py's run).

## Data (single source, Make reads the generated adapters)

| data | adapter (`just generate-term-data`) | included by | holds |
|---|---|---|---|
| `makefiles/tests/tests.test.yaml` | `tests.test.inc.mk` | `tests.inc.mk` (top) | export of TESTRUNNER_RESET_AFTER_TERM, `TESTS ?= $(PROBE_TESTS)`, `TEST_DEPS += $(TERMDEPS)`, `TEST_EXECUTOR(_FLAGS) ?=` |
| `test.yaml` | `test.inc.mk` | `Makefile.include` (after the directory defaults) | `RIOTPROJECT ?= $(PROBE_RIOTPROJECT)`, `DLCACHE_DIR ?= $(RIOTBASE)/.dlcache` |
| `makefiles/setup_dirs.test.yaml` | `setup_dirs.test.inc.mk` | `setup_dirs.inc.mk` (end) | `PYTHONPATH := $(RIOTBASE)/dist/pythonlibs/:$(PYTHONPATH)` |

The format is the one of the terminal data (`dist/tools/term/README.md`,
data kind `test`). The probes `PROBE_TESTS` and `PROBE_RIOTPROJECT` keep the
text of Make's former lines in `makefiles/term_providers.inc.mk`, which
`Makefile.include` now includes before the directories (it holds recursive
values only); test.py computes them. PYTHONPATH sits at the end of
`setup_dirs.inc.mk` because RIOTBASE is absolute from there on and nothing
between there and its former place reads it.

## Rules and tests

| rule (Make file:line, base) | test.py | tests |
|---|---|---|
| TESTS default (tests.inc.mk:9-10) | `probe_tests` | A1, D3, P1-P2 (`probe`, `available-probe`) |
| RIOTPROJECT (Makefile.include:66) | `probe_riotproject` | A2, D2, D3, P2 |
| DLCACHE_DIR, PYTHONPATH (Makefile.include:72, :138), abspath (setup_dirs.inc.mk:33, :39) | `directories` | D2, A7, P2 (`environment`) |
| docker branch (tests.inc.mk:26-28, docker.inc.mk:31-33, :41-46), TEST_DEPS (tests.inc.mk:31) | `in_docker_goal`, `check_scope` | A3, P3 (`docker`) |
| MAKEFLAGS of the environment | `check_environment` | A3, A8 |
| loop (tests.inc.mk:32-34), `$(Q)` (Makefile.include:270-274) | `recipe_test`, `quiet` | A4, P1-P2 (`two`, `executor`, `quiet0`, `fails`) |
| test/available (tests.inc.mk:37-48) | `recipe_available` | A5, P1-P2 (`available*`, `whitelist-*`, `blacklist-*`) |
| MAKEFLAGS/MFLAGS/MAKELEVEL (GNU Make 4.3, Makefile.include:3, :82-101, :272) | `makeflags`, `quote_for_env` | A6, P2 (`quoting`, `quiet0`), R1 |
| export set, target export (tests.inc.mk:6), working directory | `plan_test`, `main` | A7, A8, P2 |
| no make, no Make file | whole tool | N1-N4 |
| data and adapters | `tests.test.yaml`, `test.yaml`, `setup_dirs.test.yaml` | D1-D4 |
| Make keeps its rules, live Make = golden, recipes, register | — | R1, R3, O1 |

Test modules: `tests/test_data.py` (D), `test_algorithm.py` (A),
`test_parity.py` (P), `test_no_make.py` (N), `test_transition.py` (R, O).
The golden files `tests/golden/<app>__nrf52840dk.txt` are recorded from GNU
Make on the base (`git archive db4fc1c576`, `tests/record_golden.py`); the
cases are in `tests/tsample.py`. Run: `dist/tools/migration/run_tests.py
--step g2b-03-test`.

## Deviations and limits

- **Script environment (decision B, 2026-11-22):** the parity is for the
  variables the scripts read (`TEST_READS` in `tests/tsample.py`:
  dist/pythonlibs/testrunner, MAKEFLAGS, MFLAGS, MAKELEVEL, BOARD, USEMODULE,
  the directories). About 45 further variables Make exports are not given
  to the scripts or differ: their values are set in Make files that are not
  data (`docker.inc.mk`: DOCKER_*, INSIDE_DOCKER; `kconfig.mk`: KCONFIG_*;
  `mcuboot.mk`: IMAGE_HDR_SIZE; `Makefile.include`: Q, QQ, DLCACHE,
  UNZIP_HERE, RIOTKCONFIG, RIOT_TEST_HASH_DIR; defaults of exported but unset
  variables such as CARGO_TARGET_DIR, RUSTFLAGS, OBJDUMPFLAGS; Make exports
  unset ones as empty). FEATURES_REQUIRED and INCLUDES differ in blanks only.
- **T2:** `spawn.py` is unchanged: the terminal inside a test is still opened
  by `make cleanterm` (and the board reset by `make reset`). `just test`
  starts the scripts without Make; the scripts may call make. The no-make
  proof (N1-N4) is for test.py and the recipes, with the recorder as script.
- **T3:** no deviation: MAKEFLAGS is Make's text of `make -C <app> test
  VAR=VALUE…` (the `w` comes from `-C`).
- **T6, BUILD_IN_DOCKER=1 (decision of 2026-11-22: as Make):** Make defers
  `test` to Docker only if BUILD_IN_DOCKER=1, it is not inside a container
  (`makefiles/docker.inc.mk:41-46`) and `test` is in DOCKER_MAKECMDGOALS,
  i.e. BOARD is `native%` (`docker.inc.mk:31-33`, `tests.inc.mk:26-28`).
  Then test.py exits 3 (native boards have no data anyway); otherwise, e.g.
  on nrf52840dk, it runs the tests here as Make does (golden case `docker`).
- **T7:** `make flash test` is two calls: `just flash …` then `just test …`.
- **T4:** test-as-root, test-with-config (and test-input-hash) stay in Make.
- TESTRUNNER_CONNECT_DELAY of `boards/common/makefiles/stdio_cdc_acm.dep.mk`
  and of other boards is not data; the scope (nrf52840dk) does not reach it.
- Duplicate assignments of one variable on the command line keep the last
  value for the evaluation; MAKEFLAGS lists every assignment, as Make does.
