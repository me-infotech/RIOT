# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

DIRS += $(dir $(wildcard $(addsuffix /Makefile,$(USEMODULE))))

ifneq (,$(filter saul_init_devs,$(USEMODULE)))
  DIRS += saul/init_devs
endif

include $(RIOTBASE)/Makefile.base
