# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

# make all code end up in "ztimer_core.a"
MODULE := ztimer_core

# ensure that "ztimer_foo" builds "ztimer_foo.c", not "ztimer_core_foo.c"
BASE_MODULE := ztimer

# ztimer_core files
SRC := core.c util.c periodic.c

# enable submodules
SUBMODULES := 1
include $(RIOTBASE)/Makefile.base
