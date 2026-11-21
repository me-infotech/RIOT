# Generated from build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change build.yaml and run `just generate-config-data`.
# The build part of cpu/nrf5x_common/Makefile.include, which includes this file.

CFLAGS += $(patsubst %,-DCPU_FAM_%,$(call uppercase_and_underscore,$(CPU_FAM)))
ROM_START_ADDR ?= 0x00000000
RAM_START_ADDR ?= 0x20000000
LINKER_SCRIPT ?= cortexm.ld
INCLUDES += -I$(RIOTCPU)/nrf5x_common/include
INCLUDES += -I$(BUILD_DIR)/nrf5x_nrfx_mdk/$(CPU_FAM)
