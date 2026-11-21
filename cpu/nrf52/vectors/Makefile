# Generated from module.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change module.yaml and run `just generate-config-data`.

MODULE = nrf52_vectors
NO_AUTO_SRC = 1
SRC_FILE = vectors_$(CPU_MODEL).c
SRCS += $(SRC_FILE)

# (file triggers compiler bug. see #5775)
SRC_NOLTO += $(SRC_FILE)
include $(RIOTBASE)/Makefile.base
