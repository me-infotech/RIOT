# The flags and include directories of newlib are build data:
# makefiles/libc/newlib.build.yaml. The file included here (twice, in two
# sections) is generated from it (`just generate-config-data`); edit the
# YAML, not it. The search for newlib.h is a probe:
# makefiles/build_providers.inc.mk.

# Note on `realpath` vs `abspath`
#
# `realpath` is used instead of `abspath` to support Mingw32
# It fixes issues when using windows formatted paths like in the gcc output
# It does leave the trailing `/` on windows though

# Search for newlib.h if the standard search path of the compiler does not
# have it:
# Since Clang is not installed as a separate instance for each crossdev target
# we need to tell it where to look for platform specific includes (Newlib
# headers instead of Linux/Glibc headers.)
# On GCC this is done when building the cross compiler toolchain so we do not
# actually need to specify the include paths for system includes.
# Ubuntu gcc-arm-embedded toolchain (https://launchpad.net/gcc-arm-embedded)
# places newlib headers in several places, but the primary source seem to be
# /etc/alternatives/gcc-arm-none-eabi-include
# Gentoo Linux crossdev place the newlib headers in /usr/arm-none-eabi/include
# Arch Linux also place the newlib headers in /usr/arm-none-eabi/include
# Ubuntu seem to put a copy of the newlib headers in the same place as
# Gentoo crossdev, but we prefer to look at /etc/alternatives first.
# On OSX, newlib includes are possibly located in
# /usr/local/opt/arm-none-eabi*/arm-none-eabi/include or /usr/local/opt/gcc-arm/arm-none-eabi/include
NEWLIB_INCLUDE_PATTERNS ?= \
  /etc/alternatives/gcc-$(TARGET_ARCH)-include \
  /usr/$(TARGET_ARCH)/include \
  /usr/local/opt/$(TARGET_ARCH)*/$(TARGET_ARCH)/include \
  /usr/local/opt/gcc-*/$(TARGET_ARCH)/include \
  #
# Use the wildcard Makefile function to search for existing directories matching
# the patterns above. We use the -isystem gcc/clang argument to add the include
# directories as system include directories, which means they will not be
# searched until after all the project specific include directories (-I/path)

RIOT_BUILD_SECTION := flags
include $(RIOTMAKE)/libc/newlib.build.mk

ifeq ($(TOOLCHAIN),llvm)
  # A cross GCC already knows the target libc include path (build-in at compile time)
  # but Clang, when cross-compiling, needs to be told where to find the headers
  # for the system being built.
  # We also add -nostdinc to avoid including the host system headers by mistake
  # in case some header is missing from the cross tool chain
  NEWLIB_INCLUDES := -isystem $(NEWLIB_INCLUDE_DIR) -nostdinc
  NEWLIB_INCLUDES += $(addprefix -isystem ,$(realpath $(wildcard $(dir $(NEWLIB_INCLUDE_DIR))/usr/include)))

  # Newlib includes should go before GCC includes. This is especially important
  # when using Clang, because Clang will yield compilation errors on some GCC-
  # bundled headers. Clang compatible versions of those headers are already
  # provided by Newlib, so placing this directory first will eliminate those problems.
  # The above problem was observed with LLVM 3.9.1 when building against GCC 6.3.0 headers.
  INCLUDES := $(NEWLIB_INCLUDES) $(INCLUDES)
endif

RIOT_BUILD_SECTION := nano
include $(RIOTMAKE)/libc/newlib.build.mk
