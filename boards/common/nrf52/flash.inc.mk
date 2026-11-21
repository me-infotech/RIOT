# Generated from flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change flash.yaml and run `just generate-flash-data`.

# set list of supported programmers
PROGRAMMERS_SUPPORTED += openocd
PROGRAMMERS_SUPPORTED += bmp

# keep name of `JLINK` in sync with script jlink.sh in $(RIOTTOOLS)/jlink
JLINK ?= JLinkExe

# J-Link if its J-Link Commander is installed, OpenOCD otherwise
ifneq (,$(shell command -v $(JLINK)))
  PROGRAMMER ?= jlink
else
  PROGRAMMER ?= openocd
endif

# Setup OpenOCD for flashing. The nRF52 series is supported from OpenOCD v0.11
# onwards.
OPENOCD_DEBUG_ADAPTER ?= jlink
OPENOCD_CONFIG = $(RIOTBOARD)/common/nrf52/dist/openocd.cfg

# From Build Code Fxx and later, the nRF52 device is automatically locked after
# a power cycle and has to be recovered with a separate command after the
# initialization. Otherwise the Flash can not be accessed.
OPENOCD_POST_INIT_CMDS = -c 'nrf52_recover'
