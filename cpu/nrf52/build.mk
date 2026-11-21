# Generated from build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change build.yaml and run `just generate-config-data`.
# The build part of cpu/nrf52/Makefile.include, which includes this file.

# Export internal ROM alignment and slot sizes for bootloader support
export MCUBOOT_IMAGE_ALIGN = 8
export MCUBOOT_SLOT0_SIZE = 0x8000
export MCUBOOT_SLOT1_SIZE = 0x3C000
export MCUBOOT_SLOT2_SIZE = 0x3C000

# Set ROM and RAM lengths according to CPU model

ifneq (,$(filter nrf52805xxaa nrf52810xxaa nrf52811xxaa,$(CPU_MODEL)))
  ROM_LEN ?= 0x30000
  RAM_LEN ?= 0x6000
endif

ifneq (,$(filter nrf52820xxaa,$(CPU_MODEL)))
  ROM_LEN ?= 0x40000
  RAM_LEN ?= 0x8000
endif

ifneq (,$(filter nrf52832xxaa,$(CPU_MODEL)))
  ROM_LEN ?= 0x80000
  RAM_LEN ?= 0x10000
endif

ifneq (,$(filter nrf52833xxaa,$(CPU_MODEL)))
  ROM_LEN ?= 0x80000
  RAM_LEN ?= 0x20000
endif

ifneq (,$(filter nrf52840xxaa,$(CPU_MODEL)))
  ROM_LEN ?= 0x100000
  RAM_LEN ?= 0x40000
endif

include $(RIOTCPU)/nrf5x_common/Makefile.include
include $(RIOTMAKE)/arch/cortexm.inc.mk
