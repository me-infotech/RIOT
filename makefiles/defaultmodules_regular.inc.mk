# Generated from defaultmodules_regular.inc.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change defaultmodules_regular.inc.yaml and run `just generate-config-data`.

# This file declares DEFAULT_MODULEs that MAY have dependencies themselves
# and whose dependencies MAY have dependencies as well.
# These DEFAULT_MODULEs MUST only be disabled at application level or
# in BOARD/CPU Makefile.default.

DEFAULT_MODULE += board
DEFAULT_MODULE += board_common_init
DEFAULT_MODULE += cpu
DEFAULT_MODULE += core
DEFAULT_MODULE += core_init
DEFAULT_MODULE += core_lib
DEFAULT_MODULE += core_msg
DEFAULT_MODULE += core_panic
DEFAULT_MODULE += core_thread
DEFAULT_MODULE += sys
DEFAULT_MODULE += libc

# Include potentially added default modules by the board
-include $(BOARDDIR)/Makefile.default

# Include potentially added default modules by the CPU
-include $(RIOTCPU)/$(CPU)/Makefile.default
