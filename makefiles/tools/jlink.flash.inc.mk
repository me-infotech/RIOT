# Generated from jlink.flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change jlink.flash.yaml and run `just generate-flash-data`.

FLASHER ?= $(RIOTTOOLS)/jlink/jlink.sh
FLASHFILE ?= $(ELFFILE)
FFLAGS ?= flash $(FLASHFILE)
JLINK_SERIAL ?= $(DEBUG_ADAPTER_ID)
JLINK_IF ?=
JLINK_RESET_FILE ?=
JLINK_PRE_FLASH ?=
JLINK_POST_FLASH ?=
JLINK_FLASH_TARGETS = flash flash%
JLINK_DEBUG_TARGETS = debug debug-server
JLINK_TARGETS = $(JLINK_DEBUG_TARGETS) $(JLINK_FLASH_TARGETS) reset term-rtt

# Export JLINK_SERIAL to required targets
$(call target-export-variables,$(JLINK_TARGETS),JLINK_SERIAL)

# Export JLINK_DEVICE to required targets
$(call target-export-variables,$(JLINK_TARGETS),JLINK_DEVICE)

ifneq (,$(JLINK))
  # Export JLINK to required targets if not empty
  $(call target-export-variables,$(JLINK_TARGETS),JLINK)
endif

ifneq (,$(JLINK_IF))
  # Export JLINK_IF to required targets if not empty
  $(call target-export-variables,$(JLINK_TARGETS),JLINK_IF)
endif

ifneq (,$(JLINK_RESET_FILE))
  # Export JLINK_RESET_FILE to required targets if not empty
  $(call target-export-variables,$(JLINK_TARGETS),JLINK_RESET_FILE)
endif

# Export JLINK_PRE_FLASH to flash targets only if not empty (the target
# is the word JLINK_FLASH_TARGETS, as in the original Make file; GNU Make
# exports a defined variable for every target anyway)
ifneq (,$(JLINK_PRE_FLASH))
  $(call target-export-variables,JLINK_FLASH_TARGETS,JLINK_PRE_FLASH)
endif

# Export JLINK_POST_FLASH to flash targets only if not empty
ifneq (,$(JLINK_POST_FLASH))
  $(call target-export-variables,JLINK_FLASH_TARGETS,JLINK_POST_FLASH)
endif
