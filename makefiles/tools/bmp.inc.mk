# Flasher: generated from bmp.flash.yaml (step G3-2)
include $(RIOTMAKE)/tools/bmp.flash.inc.mk

DEBUGGER ?= $(RIOTTOOLS)/bmp/bmp.py
RESET ?= $(RIOTTOOLS)/bmp/bmp.py

DEBUGGER_FLAGS ?= $(BMP_OPTIONS) debug $(DEBUG_ELFFILE)
RESET_FLAGS ?= $(BMP_OPTIONS) reset
