# Generated from auto_init.inc.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change auto_init.inc.yaml and run `just generate-config-data`.

AUTO_INIT_PREFIX = auto_init_
AUTO_INIT_SRCS = $(wildcard $(AUTO_INIT_PREFIX)*.c)
AUTO_INIT_MODULES_AVAILABLE = $(patsubst $(AUTO_INIT_PREFIX)%.c,%,$(AUTO_INIT_SRCS))
AUTO_INIT_MODULES_USED = $(filter $(AUTO_INIT_MODULES_AVAILABLE),$(USEMODULE))
AUTO_INIT_MODULES_USED_SRCS = $(patsubst %,$(AUTO_INIT_PREFIX)%.c,$(AUTO_INIT_MODULES_USED))
SRC = init.c $(AUTO_INIT_MODULES_USED_SRCS)
include $(RIOTBASE)/Makefile.base
