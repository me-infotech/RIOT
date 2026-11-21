# Generated from periph.module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change periph.module.yaml and run `just generate-config-data`.

MODULE ?= periph

# enable submodules
SUBMODULES := 1

# in case of e.g., <cpu>_periph_common, use periph_* as submodule prefix
BASE_MODULE := periph
include $(RIOTBASE)/Makefile.base
