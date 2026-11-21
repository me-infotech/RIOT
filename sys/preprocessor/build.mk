# Generated from build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change build.yaml and run `just generate-config-data`.
# The build part of sys/preprocessor/Makefile.include, which includes this file.

RIOT_PP_SUCCESSOR_MAX ?= 9999
PSEUDOMODULES += preprocessor_successor
USEMODULE_INCLUDES_preprocessor := $(BINDIR)/preprocessor
USEMODULE_INCLUDES += $(USEMODULE_INCLUDES_preprocessor)
RIOT_GENERATE_PP_HEADERS :=

ifneq (,$(filter preprocessor_successor,$(USEMODULE)))
  RIOT_GENERATE_PP_HEADERS += $(BINDIR)/preprocessor/preprocessor_successor.h
endif
