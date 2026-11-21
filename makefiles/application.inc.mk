# Generated from application.inc.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change application.inc.yaml and run `just generate-config-data`.

MODULE = $(APPLICATION_MODULE)
DIRS += $(RIOTCPU)/$(CPU)
DIRS += $(BOARDDIR)
DIRS += $(RIOTBASE)/boards
DIRS += $(RIOTCPU)
DIRS += $(RIOTBASE)/core
DIRS += $(RIOTBASE)/core/lib
DIRS += $(RIOTBASE)/drivers
DIRS += $(RIOTBASE)/sys

# For regular modules, adding files to BLOBS, SRC, SRCXX, ASMSRC or ASSMSRC
# in their Makefile is sufficient to explicitely set the variables.
#
# Application modules are different, as they use this makefile to build, thus
# application level variables are not available unless exported.
#
# But exporting would pre-set the variables for all submakefiles.
#
# As workaround, $(RIOTBASE)/Makefile.include passes the above-listed variables
# to this Makefile as APPLICATION_*.
BLOBS = $(APPLICATION_BLOBS)
SRC = $(APPLICATION_SRC)
SRCXX = $(APPLICATION_SRCXX)
ASMSRC = $(APPLICATION_ASMSRC)
ASSMSRC = $(APPLICATION_ASSMSRC)
include $(RIOTBASE)/Makefile.base
