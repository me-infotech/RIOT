# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

MODULE = core_lib

# enable submodules
SUBMODULES := 1

# set this so the panic and init code is available as "core_panic" and "core_init"
# instead of "core_lib_..."
BASE_MODULE = core

# exclude submodule sources from *.c wildcard source selection
SRC := $(filter-out panic.c init.c,$(wildcard *.c))
include $(RIOTBASE)/Makefile.base
