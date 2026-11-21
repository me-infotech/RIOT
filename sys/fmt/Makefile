# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

# exclude submodule sources from *.c wildcard source selection
SRC := $(filter-out table.c,$(wildcard *.c))

# enable submodules
SUBMODULES := 1
include $(RIOTBASE)/Makefile.base
