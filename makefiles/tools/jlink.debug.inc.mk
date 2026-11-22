# Generated from jlink.debug.yaml by dist/tools/term/term.py.
# Do not edit: change jlink.debug.yaml and run `just generate-term-data`.

DEBUGGER ?= $(RIOTTOOLS)/jlink/jlink.sh
DEBUGSERVER ?= $(RIOTTOOLS)/jlink/jlink.sh
RESET ?= $(RIOTTOOLS)/jlink/jlink.sh
DEBUGGER_FLAGS ?= debug $(DEBUG_ELFFILE)
DEBUGSERVER_FLAGS ?= debug-server
RESET_FLAGS ?= reset

ifneq (,$(DBG_EXTRA_FLAGS))
  # Export OPENOCD_DBG_EXTRA_CMD only to the flash/flash-only target
  $(call target-export-variables,$(JLINK_DEBUG_TARGETS),DBG_EXTRA_FLAGS)
endif
