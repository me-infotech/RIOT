# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

# every source file but init.c is a submodule periph_<name>
PERIPH_COMMON_MODULES_SRCS_ALL = $(filter-out init.c,$(wildcard *.c))
PERIPH_COMMON_MODULES = $(patsubst %.c,periph_%,$(PERIPH_COMMON_MODULES_SRCS_ALL))
PERIPH_COMMON_MODULES_USED = $(filter $(PERIPH_COMMON_MODULES),$(USEMODULE))
SRC = init.c
SRC += $(patsubst periph_%,%.c,$(PERIPH_COMMON_MODULES_USED))
include $(RIOTBASE)/Makefile.base
