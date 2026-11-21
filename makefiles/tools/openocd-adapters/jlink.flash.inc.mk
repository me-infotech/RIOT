# Generated from jlink.flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change jlink.flash.yaml and run `just generate-flash-data`.

# Segger J-Link debug adapter
OPENOCD_ADAPTER_INIT ?= -c 'source [find interface/jlink.cfg]'

# default to SWD
OPENOCD_TRANSPORT ?= swd
