# Generated from programmer.flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change programmer.flash.yaml and run `just generate-flash-data`.

# Configure the programmer related variables
PROGRAMMER_QUIET ?= $(QUIET)

ifeq ($(PROGRAMMER_QUIET),0)
  PROGRAMMER_VERBOSE_OPT ?= --verbose
endif

# Don't use the programmer wrapper by default
USE_PROGRAMMER_WRAPPER_SCRIPT ?= 0

ifeq ($(USE_PROGRAMMER_WRAPPER_SCRIPT),1)
  PROGRAMMER_FLASH ?= @$(RIOTTOOLS)/programmer/programmer.py --action Flashing --cmd "$(FLASHER) $(FFLAGS)" --programmer "$(PROGRAMMER)" $(PROGRAMMER_VERBOSE_OPT)
else
  PROGRAMMER_FLASH ?= $(FLASHER) $(FFLAGS)
endif
