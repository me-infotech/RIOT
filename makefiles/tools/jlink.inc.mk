include $(RIOTMAKE)/tools/dbg_common.inc.mk

# Flasher and the variables jlink.sh gets: generated from jlink.flash.yaml
# (step G3-2)
include $(RIOTMAKE)/tools/jlink.flash.inc.mk

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
