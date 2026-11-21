# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

MODULE = ieee802154
SRC = ieee802154.c

ifneq (,$(filter ieee802154_security,$(USEMODULE)))
  SRC += security.c
endif

ifneq (,$(filter ieee802154_submac,$(USEMODULE)))
  SRC += submac.c
endif

include $(RIOTBASE)/Makefile.base
