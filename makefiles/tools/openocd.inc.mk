include $(RIOTMAKE)/tools/dbg_common.inc.mk

# Flasher, debug adapter, configuration and the variables openocd.sh gets
# for flashing: generated from openocd.flash.yaml (step G3-2)
include $(RIOTMAKE)/tools/openocd.flash.inc.mk

DEBUGGER ?= $(RIOTTOOLS)/openocd/openocd.sh
DEBUGSERVER ?= $(RIOTTOOLS)/openocd/openocd.sh
DEBUGCLIENT ?= $(RIOTTOOLS)/openocd/openocd.sh
RESET ?= $(RIOTTOOLS)/openocd/openocd.sh

DEBUGGER_FLAGS ?= debug $(DEBUG_ELFFILE)
DEBUGSERVER_FLAGS ?= debug-server
DEBUGCLIENT_FLAGS ?= debug-client $(DEBUG_ELFFILE)
RESET_FLAGS ?= reset

ifneq (,$(OPENOCD_CMD_RESET_RUN))
  # Export OPENOCD_CMD_RESET_RUN only to the reset target
  $(call target-export-variables,reset,OPENOCD_CMD_RESET_RUN)
endif

OPENOCD_DEBUG_TARGETS = debug debugr debug-server debug-client

ifneq (,$(OPENOCD_DBG_EXTRA_CMD))
  # Export OPENOCD_DBG_EXTRA_CMD only to the flash/flash-only target
  $(call target-export-variables,$(OPENOCD_DEBUG_TARGETS),OPENOCD_DBG_EXTRA_CMD)
endif

ifneq (,$(DBG_EXTRA_FLAGS))
  # Export OPENOCD_DBG_EXTRA_CMD only to the flash/flash-only target
  $(call target-export-variables,$(OPENOCD_DEBUG_TARGETS),DBG_EXTRA_FLAGS)
endif
