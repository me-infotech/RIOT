# Generated from bmp.flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change bmp.flash.yaml and run `just generate-flash-data`.

FLASHER ?= $(RIOTTOOLS)/bmp/bmp.py
FLASHFILE ?= $(ELFFILE)
FFLAGS ?= $(BMP_OPTIONS) flash $(FLASHFILE)
