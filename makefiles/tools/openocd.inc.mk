include $(RIOTMAKE)/tools/dbg_common.inc.mk

# Flasher, debug adapter, configuration and the variables openocd.sh gets
# for flashing: generated from openocd.flash.yaml (step G3-2)
include $(RIOTMAKE)/tools/openocd.flash.inc.mk

# Debugger, debug server and client, reset and the variables they get:
# generated from openocd.debug.yaml (step G2B-1)
include $(RIOTMAKE)/tools/openocd.debug.inc.mk
