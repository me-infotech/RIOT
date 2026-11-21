# Generated from build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change build.yaml and run `just generate-config-data`.
# The build part of Makefile.include, which includes this file once per
# section with RIOT_BUILD_SECTION set to the name of the section.

ifeq (flags,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  export RIOTBUILD_CONFIG_HEADER_C = $(BINDIR)/riotbuild/riotbuild.h
  # QUIET is set by the application
  QUIET ?= 1
  # Set this to 1 to enable pretty-printing the assert location in addition
  # to the address of the failing assert.
  # This saves you to resolve the address manually with addr2line at the cost
  # of greater ROM consumption.
  VERBOSE_ASSERT ?= 0
  ifeq ($(VERBOSE_ASSERT),1)
    CFLAGS += -DDEBUG_ASSERT_VERBOSE
    DEVELHELP := 1
  endif
  # Set this to 1 to enable code in RIOT that does safety checking
  # which is not needed in a production environment but helps in the
  # development process:
  DEVELHELP ?= 0
  ifeq ($(DEVELHELP),1)
    CFLAGS += -DDEVELHELP
  endif
  # Set this to 1 to enable thread names
  THREAD_NAMES ?= 0
  ifeq ($(THREAD_NAMES),1)
    CFLAGS += -DCONFIG_THREAD_NAMES
  endif
  # Override LOG_LEVEL if variable is set and if CFLAGS doesn't already contain
  # a LOG_LEVEL config
  ifdef LOG_LEVEL
    ifeq (,$(filter -DLOG_LEVEL=%,$(CFLAGS)))
      CFLAGS += -DLOG_LEVEL=$(LOG_LEVEL)
    endif
  endif
  # Fail on warnings. Can be overridden by `make WERROR=0`.
  WERROR ?= 1
  ifeq ($(WERROR),1)
    CFLAGS += -Werror
  endif
  WPEDANTIC ?= 0
  ifeq ($(WPEDANTIC),1)
    CFLAGS += -Wpedantic
  endif
  # Provide a shallow sanity check. You cannot call `make` in a module directory.
  export __RIOTBUILD_FLAG := RIOT
  # Tool saving stdin to a file only on content update.
  # It keeps the file timestamp if it would end up the same.
  LAZYSPONGE ?= $(RIOTTOOLS)/lazysponge/lazysponge.py
  LAZYSPONGE_FLAGS ?= $(if $(filter 1,$(QUIET)),,--verbose)
  # default toolchain prefix, defaults to target triple followed by a dash, you
  # will most likely not need to touch this.
  export PREFIX ?= $(if $(TARGET_ARCH),$(TARGET_ARCH)-)
  # Add standard include directories
  INCLUDES += -I$(APPDIR)
  BUILD_APP_INCLUDE_DIR = $(wildcard $(APPDIR)/include)
  INCLUDES += $(patsubst %,-I%,$(BUILD_APP_INCLUDE_DIR))
  INCLUDES += -I$(RIOTBASE)/core/lib/include
  INCLUDES += -I$(RIOTBASE)/core/include
  INCLUDES += -I$(RIOTBASE)/drivers/include
  INCLUDES += -I$(RIOTBASE)/sys/include
endif

# Include Board and CPU configuration
ifeq (board,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  BUILD_BOARD_INCLUDE_DIR = $(wildcard $(BOARDDIR)/include)
  INCLUDES += $(patsubst %,-I%,$(BUILD_BOARD_INCLUDE_DIR))
  INCLUDES += -I$(RIOTCPU)/$(CPU)/include
  # Include the Makefile.include for common boards after the specific board,
  # likewise proceed with the CPU Makefile.includes.
  include $(BOARDDIR)/Makefile.include
  include $(RIOTBASE)/boards/Makefile.include
  include $(RIOTCPU)/Makefile.include
  include $(RIOTCPU)/$(CPU)/Makefile.include
endif

ifeq (toolchain,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  # Assume GCC/GNU as supported toolchain if CPU's Makefile.include doesn't
  # provide this macro
  TOOLCHAINS_SUPPORTED ?= gnu
  # Import all toolchain settings
  include $(RIOTMAKE)/toolchain/$(TOOLCHAIN).inc.mk
  # Other than on native, RWX segments in ROM are not actually RWX, as regular
  # store instructions won't write to flash.
  ifeq (,$(filter native native32 native64,$(BOARD)))
    LINKER_SUPPORTS_NOWARNRWX ?= $(PROBE_LINK_NOWARNRWX)
    ifeq ($(LINKER_SUPPORTS_NOWARNRWX),1)
      LINKFLAGS += -Wl,--no-warn-rwx-segments
    endif
  endif
  # Append ldscript path after importing CPU and board makefiles to allow
  # overriding the core ldscripts
  LINKFLAGS += -L$(RIOTBASE)/core/ldscripts
endif

ifeq (version,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  # Tell ccache to pass the original file to the compiler, instead of passing the
  # preprocessed code. Without this setting, the compilation will fail with
  # -Wimplicit-fallthrough warnings even when the fall through case is properly
  # commented because the preprocessor has stripped the comments from the code.
  # This also fixes some other false warnings when compiling with LLVM/Clang.
  # The environment variable only affects builds with ccache (e.g. on CI/Murdock).
  # Non cached builds are not affected in any way.
  # For more information, see http://petereisentraut.blogspot.com/2011/09/ccache-and-clang-part-2.html
  export CCACHE_CPP2 = yes
  # set some settings useful for continuous integration builds
  ifeq ($(RIOT_CI_BUILD),1)
    RIOT_VERSION ?= buildtest
  endif
  # if you want to publish the board into the sources as an uppercase #define
  BOARDDEF = $(call uppercase_and_underscore,$(BOARD))
  CPUDEF = $(call uppercase_and_underscore,$(CPU))
  CFLAGS += -DRIOT_APPLICATION=\"$(APPLICATION)\"
  CFLAGS += -DBOARD_$(BOARDDEF)=\"$(BOARD)\"
  CFLAGS += -DRIOT_BOARD=BOARD_$(BOARDDEF)
  CFLAGS += -DCPU_$(CPUDEF)=\"$(CPU)\"
  CFLAGS += -DRIOT_CPU=CPU_$(CPUDEF)
  # Feature test default CFLAGS and LINKFLAGS for the set compiled.
  include $(RIOTMAKE)/cflags.inc.mk
  # Include VERSION for releases (not data, outside the build data if present)
  -include $(RIOTBASE)/VERSION
  -include $(RIOTBASE)/EXTRAVERSION
  include $(RIOTMAKE)/git_version.inc.mk
  RIOT_VERSION ?= $(RIOT_VERSION_GIT)
  RIOT_DUMMY_VERSION ?= 2042.5.23
  RIOT_EXTRAVERSION ?= 0
  # Generate machine readable RIOT_VERSION macro. This will fall-back to
  # RIOT_DUMMY_VERSION if RIOT_VERSION is invalid (e.g. during CI builds).
  # BUILD_RIOT_VERSION_TUPLE: `version_tuple` of RIOT_VERSION, else of
  # RIOT_DUMMY_VERSION (build algorithm).
  RIOT_VERSION_CODE ?= RIOT_VERSION_NUM\($(BUILD_RIOT_VERSION_TUPLE),$(RIOT_EXTRAVERSION)\)
  # add extra include paths for packages in $(USEMODULE)
  USEMODULE_INCLUDES =
  # include global Makefile.include for `sys` modules
  include $(RIOTBASE)/sys/Makefile.include
  # include Makefile.includes of each driver modules if they exist
  -include $(USEMODULE:%=$(RIOTBASE)/drivers/%/Makefile.include)
  # include Makefile.includes for packages in $(PKG_PATHS)
  -include $(PKG_PATHS:%=%Makefile.include)
  # include external modules configuration
  -include $(EXTERNAL_MODULE_PATHS:%=%Makefile.include)
  # Deduplicate includes without sorting them (`uniq`, defined in Makefile.include)
  INCLUDES += $(patsubst %,-I%,$(strip $(call uniq,$(USEMODULE_INCLUDES))))
  # include bindist target
  include $(RIOTMAKE)/bindist.inc.mk
endif

ifeq (files,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  ELFFILE ?= $(BINDIR)/$(APPLICATION).elf
  HEXFILE ?= $(patsubst %.elf,%.hex,$(ELFFILE))
  BINFILE ?= $(patsubst %.elf,%.bin,$(ELFFILE))
  HASHFILE ?= $(BINFILE)
  MAPFILE ?= $(patsubst %.elf,%.map,$(ELFFILE))
endif

ifeq (link,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  BUILD_FILES += $(ELFFILE)
  BUILD_FILES += $(BINFILE)
  BUILD_FILES += $(FLASHFILE)
  BUILD_FILES += $(HASHFILE)
  # variables used to compile and link c++
  ifneq (,$(filter cpp,$(USEMODULE)))
    CPPMIX ?= 1
  endif
  # We assume $(LINK) to be gcc-like. Use `LINKFLAGPREFIX :=` for ld-like linker options.
  LINKFLAGPREFIX ?= -Wl,
  # Also build external modules
  DIRS += $(EXTERNAL_MODULE_PATHS)
  # GENSRC (generated sources of packages) is made accessible to subprocesses
  export GENSRC
endif

ifeq (vars,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  # Export variables used throughout the whole make system:
  include $(RIOTMAKE)/vars.inc.mk
endif

ifeq (header,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  # The configuration header riotbuild.h (rules in Makefile.include):
  # BUILD_EXTDEFINES are the MODULE_* defines of makefiles/modules.inc.mk
  # (build algorithm).
  CFLAGS_WITH_MACROS += $(CFLAGS)
  CFLAGS_WITH_MACROS += -DRIOT_VERSION=\"$(RIOT_VERSION)\"
  CFLAGS_WITH_MACROS += -DRIOT_VERSION_CODE=$(RIOT_VERSION_CODE)
  # To allow package code easily check if compiled against RIOT or not:
  CFLAGS_WITH_MACROS += -DRIOT_OS=1
  ifneq (,$(RIOT_VERSION_EXTRA))
    CFLAGS_WITH_MACROS += -DCONFIG_RIOT_VERSION_EXTRA=\""$(RIOT_VERSION_EXTRA)"\"
  endif
  # MODULE_NAME defines. Declared in 'makefiles/modules.inc.mk'
  CFLAGS_WITH_MACROS += $(BUILD_EXTDEFINES)
  CFLAGS += -include
  CFLAGS += '$(RIOTBUILD_CONFIG_HEADER_C)'
endif

ifneq (,$(RIOT_BUILD_SECTION))
  $(error Makefile.include: no build section $(RIOT_BUILD_SECTION))
endif
