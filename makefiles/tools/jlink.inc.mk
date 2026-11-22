include $(RIOTMAKE)/tools/dbg_common.inc.mk

# Flasher and the variables jlink.sh gets: generated from jlink.flash.yaml
# (step G3-2)
include $(RIOTMAKE)/tools/jlink.flash.inc.mk

# Debugger, debug server and reset: generated from jlink.debug.yaml
# (step G2B-1)
include $(RIOTMAKE)/tools/jlink.debug.inc.mk
