# Generated from term.yaml by dist/tools/term/term.py.
# Do not edit: change term.yaml and run `just generate-term-data`.

# On Blackmagic Probe, the first ACM is used to connect to the gdb server,
# the second is the BMP's UART interface
ifeq ($(PROGRAMMER),bmp)
  PORT_LINUX ?= /dev/ttyACM1
  PORT_DARWIN ?= $(word 2,$(PROBE_TTY_USBMODEM))
endif
