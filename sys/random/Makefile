# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

SRC := random.c
BASE_MODULE := prng
SUBMODULES := 1

ifneq (,$(filter prng_fortuna,$(USEMODULE)))
  DIRS += fortuna
endif

ifneq (,$(filter prng_tinymt32,$(USEMODULE)))
  DIRS += tinymt32
endif

include $(RIOTBASE)/Makefile.base
