# Generated from gnu.build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change gnu.build.yaml and run `just generate-config-data`.
# The build part of makefiles/toolchain/gnu.inc.mk, which includes this file.

CC = $(PREFIX)gcc
CXX = $(PREFIX)g++
CCAS ?= $(CC)

ifeq ($(LTO),1)
  AR = $(PREFIX)gcc-ar
  RANLIB = $(PREFIX)gcc-ranlib
else
  AR = $(PREFIX)ar
  RANLIB = $(PREFIX)ranlib
endif

AS = $(PREFIX)as
NM = $(PREFIX)nm
LINK = $(PREFIX)gcc
LINKXX = $(PREFIX)g++
SIZE = $(PREFIX)size

# the first of PREFIX-objcopy, gobjcopy, objcopy on PATH
OBJCOPY ?= $(PROBE_OBJCOPY)

ifeq ($(OBJCOPY),)
  $(warning objcopy not found. Hex file will not be created.)
  OBJCOPY = true
endif

# Default to the native (g)objdump, helps when using toolchain from docker
OBJDUMP ?= $(PROBE_OBJDUMP)

# Parse only the major version of GCC (empty without compiler)
GCC_VERSION := $(PROBE_GCC_VERSION)

# -fmacro-prefix-map requires GCC 8
ifneq (1,$(call version_is_greater_or_equal,$(GCC_VERSION),8))
  OPTIONAL_CFLAGS_BLACKLIST += -fmacro-prefix-map=$(RIOTBASE)/=
  OPTIONAL_CFLAGS_BLACKLIST += -fdebug-prefix-map=$(RIOTBASE)/=
endif

# GCC does not warn about documentation (yet)
OPTIONAL_CFLAGS_BLACKLIST += -Wdocumentation
OPTIONAL_CFLAGS_BLACKLIST += -Wno-error=documentation
OPTIONAL_CFLAGS_BLACKLIST += -Wno-documentation-deprecated-sync

# GCC's static analysis tools can be enabled using -fanalyzer
CFLAGS_STATIC_ANALYSIS := -fanalyzer

# Data address spaces starts at zero for all supported architectures. This fixes
# compilation at least on MSP430 and AVR.
# See https://gcc.gnu.org/bugzilla/show_bug.cgi?id=105523
ifneq (,$(filter $(GCC_VERSION),12 13))
  CFLAGS += --param=min-pagesize=0
endif
