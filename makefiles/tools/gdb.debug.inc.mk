# Generated from gdb.debug.yaml by dist/tools/term/term.py.
# Do not edit: change gdb.debug.yaml and run `just generate-term-data`.

export GDBPREFIX ?= $(PREFIX)

# If the user installed a magic single target GDB rather than just using
# gdb-multiarch, there typically is a reason for it - e.g. missing support for
# that particular target in gdb-multiarch.
ifeq ($(PROBE_GDB_STATUS),0)
  export GDB ?= $(GDBPREFIX)gdb
else
  # gdb-multiarch is normally
  export GDB ?= gdb-multiarch
endif
