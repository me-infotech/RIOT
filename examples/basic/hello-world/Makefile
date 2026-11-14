# The application settings are in riot-app.yaml; riot-app.inc.mk is generated
# from it (`just generate-app-config` in the root of the RIOT repository).
# Its path is taken from this Makefile, so `make -f <dir>/Makefile` finds it.
RIOT_APP_CONFIG_MK := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/riot-app.inc.mk
ifeq (,$(wildcard $(RIOT_APP_CONFIG_MK)))
  $(error $(RIOT_APP_CONFIG_MK) missing: run 'just generate-app-config' in the RIOT root)
endif
include $(RIOT_APP_CONFIG_MK)

include $(RIOTBASE)/Makefile.include
