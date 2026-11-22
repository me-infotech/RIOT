# Generated from bmp.debug.yaml by dist/tools/term/term.py.
# Do not edit: change bmp.debug.yaml and run `just generate-term-data`.

DEBUGGER ?= $(RIOTTOOLS)/bmp/bmp.py
RESET ?= $(RIOTTOOLS)/bmp/bmp.py
DEBUGGER_FLAGS ?= $(BMP_OPTIONS) debug $(DEBUG_ELFFILE)
RESET_FLAGS ?= $(BMP_OPTIONS) reset
