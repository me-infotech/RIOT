# Generated from newlib.build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change newlib.build.yaml and run `just generate-config-data`.
# The build part of makefiles/libc/newlib.mk, which includes this file once per
# section with RIOT_BUILD_SECTION set to the name of the section.

ifeq (flags,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  ifneq (,$(filter newlib_nano,$(USEMODULE)))
    # Test if nano.specs is available
    ifeq ($(PROBE_LINK_NANO_SPECS),0)
      USE_NEWLIB_NANO = 1
      ifeq ($(PROBE_LINK_NANO_WCHAR_WARNING),0)
        CFLAGS += -fshort-wchar
        LINKFLAGS += -Wl,--no-wchar-size-warning
      endif
    endif
  endif
  ifneq (,$(filter newlib_gnu_source,$(USEMODULE)))
    CFLAGS += -D_GNU_SOURCE=1
  endif
  ifeq ($(USE_NEWLIB_NANO),1)
    LINKFLAGS += -specs=nano.specs
  endif
  LINKFLAGS += -lc
  # Search for Newlib include directories
  ifeq ($(NEWLIB_INCLUDE_DIR),)
    NEWLIB_INCLUDE_DIR := $(PROBE_NEWLIB_INCLUDE_DIR)
  endif
endif

ifeq (nano,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  ifeq ($(USE_NEWLIB_NANO),1)
    NEWLIB_NANO_INCLUDE_DIR ?= $(PROBE_NEWLIB_NANO_INCLUDE_DIR)
    ifneq (,$(NEWLIB_NANO_INCLUDE_DIR))
      # newlib-nano overrides newlib.h and its include dir should therefore go before
      # the regular system include dirs.
      INCLUDES := -isystem $(NEWLIB_NANO_INCLUDE_DIR) $(INCLUDES)
    endif
  endif
  # In case externally compiled code gets linked in, it may use newlib's assert
  # implementation. We wrap that to RIOT's assert implementation for consistency.
  LINKFLAGS += -Wl,-wrap=__assert_func
endif

ifneq (,$(RIOT_BUILD_SECTION))
  $(error makefiles/libc/newlib.mk: no build section $(RIOT_BUILD_SECTION))
endif
