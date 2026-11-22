# Generated from debug.yaml by dist/tools/term/term.py.
# Do not edit: change debug.yaml and run `just generate-term-data`.

# elf file used for the debugger, must include bootloader offset
DEBUG_ELFFILE ?= $(ELFFILE)

# Check if setsid command is available on the system for debug target
# This is not the case on MacOSX, so it must be built on the fly
# (the export names the value of SETSID, as Make did before: Make's text kept)
ifeq ($(OS),Darwin)
  ifneq (,$(filter debug,$(MAKECMDGOALS)))
    ifeq (,$(shell command -v setsid 2>/dev/null))
      SETSID = $(RIOTTOOLS)/setsid/setsid
      $(call target-export-variables,debug,$(SETSID))
      DEBUGDEPS += $(SETSID)
    endif
  endif
endif
