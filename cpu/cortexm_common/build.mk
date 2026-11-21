# Generated from build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change build.yaml and run `just generate-config-data`.
# The build part of cpu/cortexm_common/Makefile.include, which includes this file.

# include module specific includes
INCLUDES += -I$(RIOTCPU)/cortexm_common/include

# All variables must be defined in the CPU configuration when using the common
# `ldscripts/cortexm.ld`
ifneq (,$(ROM_START_ADDR)$(RAM_START_ADDR)$(ROM_LEN)$(RAM_LEN))
  ifeq ($(ROM_START_ADDR),)
    $(error ROM_START_ADDR is not defined)
  endif
  ifeq ($(RAM_START_ADDR),)
    $(error RAM_START_ADDR is not defined)
  endif
  ifeq ($(ROM_LEN),)
    $(error ROM_LEN is not defined)
  endif
  ifeq ($(RAM_LEN),)
    $(error RAM_LEN is not defined)
  endif
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_rom_start_addr=$(ROM_START_ADDR)
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_ram_start_addr=$(RAM_START_ADDR)
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_rom_length=$(ROM_LEN)
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_ram_length=$(RAM_LEN)
endif

ifneq (,$(BACKUP_RAM_LEN))
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_backup_ram_start_addr=$(BACKUP_RAM_ADDR)
  LINKFLAGS += $(LINKFLAGPREFIX)--defsym=_backup_ram_len=$(BACKUP_RAM_LEN)
  CFLAGS += -DCPU_HAS_BACKUP_RAM=1
endif

TOOLCHAINS_SUPPORTED = gnu llvm

# Only define the linker symbol if the variable is set
# The variable can be set using target specific variable thanks to lazy evaluation

# ROM_OFFSET: offset in rom to start linking, allows supporting a bootloader
LINKFLAGS += $(if $(ROM_OFFSET),$(LINKFLAGPREFIX)--defsym=_rom_offset=$(ROM_OFFSET))

# FW_ROM_LEN: rom length to use for firmware linking. Allows linking only in a section of the rom.
LINKFLAGS += $(if $(FW_ROM_LEN),$(LINKFLAGPREFIX)--defsym=_fw_rom_length=$(FW_ROM_LEN))
