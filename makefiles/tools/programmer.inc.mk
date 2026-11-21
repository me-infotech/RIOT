# Configure the programmer related variables; the flash command is
# generated from programmer.flash.yaml (step G3-2)
include $(RIOTMAKE)/tools/programmer.flash.inc.mk

ifeq (1,$(USE_PROGRAMMER_WRAPPER_SCRIPT))
  PROGRAMMER_RESET ?= @$(RIOTTOOLS)/programmer/programmer.py \
  --action Resetting --cmd "$(RESET) $(RESET_FLAGS)" \
  --programmer "$(PROGRAMMER)" $(PROGRAMMER_VERBOSE_OPT)
else
  PROGRAMMER_RESET ?= $(RESET) $(RESET_FLAGS)
endif
