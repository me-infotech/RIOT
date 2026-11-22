# Values the terminal, debugger and test data read but do not define (steps
# G2B-1, G2B-3).
#
# The terminal, debugger and test data (makefiles/tools/serial.term.yaml,
# boards/common/nrf52/term.yaml, makefiles/tools/gdb.debug.yaml,
# makefiles/tests/tests.test.yaml, dist/tools/term/README.md) read the answers of the shell as PROBE_*
# variables, as the build data reads the toolchain probes
# (makefiles/build_providers.inc.mk, step G0-3). The terminal without Make
# computes them in Python (dist/tools/term/term.py); for Make, which reads the
# Make files generated from the data, this file defines them with the
# commands the Make files used before. They are recursive, so each one runs
# when the data reads it, as the `$(shell …)` it replaces did.
#
# This is the algorithm, not data: it goes away with Make.

# makefiles/tools/serial.inc.mk: the TTY and serial number ttys.py finds
# (MOST_RECENT_PORT=1)
PROBE_TTY_DETECTED = $(shell $(TTY_SELECT_CMD) || echo 'no-tty-detected no-serial-detected')
# makefiles/tools/serial.inc.mk: the time stamp of the pyterm session
PROBE_DATE_TIME = $(shell date +%Y-%m-%d_%H.%M.%S)
# makefiles/tools/serial.inc.mk, boards/common/nrf52/Makefile.include: the
# USB modems of macOS, sorted
PROBE_TTY_USBMODEM = $(sort $(wildcard /dev/tty.usbmodem*))
# makefiles/tools/gdb.inc.mk: the exit status of `$(GDBPREFIX)gdb -v` (0: a
# GDB of the target is installed)
PROBE_GDB_STATUS = $(shell $(GDBPREFIX)gdb -v > /dev/null 2>&1; echo $$?)
# makefiles/tests/tests.inc.mk: the executable files of $(APPDIR)/tests (the
# default of TESTS), with the text of the former `TESTS ?=` line (step G2B-3)
PROBE_TESTS = $(foreach file,$(wildcard $(APPDIR)/tests/*[^~]),\
                        $(shell test -f $(file) -a -x $(file) && echo $(file)))
# Makefile.include: the default of RIOTPROJECT, the top directory of the git
# work tree of the calling directory or the calling directory (step G2B-3)
PROBE_RIOTPROJECT = $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)
