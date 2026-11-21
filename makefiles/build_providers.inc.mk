# Values the build data reads but does not define (step G0-3).
#
# The build data (build.yaml, *.build.yaml, dist/tools/config_data/README.md)
# reads the answers of the toolchain and git as PROBE_* variables and two
# values of the build algorithm as BUILD_* variables. The build without Make
# computes them in Python (dist/tools/cmake_gen/toolchain.py, plan.py); for
# Make, which reads the Make files generated from the data, this file defines
# them with the commands the Make files used before. They are recursive, so
# each one runs when the data reads it, as the `$(shell …)` it replaces did;
# those that were simple (`:=`) or memoized before are memoized.
#
# This is the algorithm, not data: it goes away with Make.

# makefiles/toolchain/gnu.inc.mk: the major version of the compiler
PROBE_GCC_VERSION = $(firstword $(subst ., ,$(shell command -v $(CC) > /dev/null && $(CC) -dumpversion)))
# makefiles/toolchain/gnu.inc.mk: the first objcopy and objdump on PATH
PROBE_OBJCOPY = $(call memoized,PROBE_OBJCOPY,$(shell command -v $(PREFIX)objcopy || command -v gobjcopy || command -v objcopy))
PROBE_OBJDUMP = $(call memoized,PROBE_OBJDUMP,$(or $(shell command -v $(PREFIX)objdump || command -v gobjdump),objdump))

# makefiles/cflags.inc.mk: exit status of the compiler with -std=c11/-std=c++14
PROBE_CC_STD_C11 = $(shell $(CC) -std=c11 -E - 2>/dev/null >/dev/null </dev/null ; echo $$?)
PROBE_CC_STD_CXX14 = $(shell $(CC) -std=c++14 -E - 2>/dev/null >/dev/null </dev/null ; echo $$?)
# makefiles/cflags.inc.mk, Makefile.include: 1 if the linker takes the option
PROBE_LINK_NOEXECSTACK = $(shell LC_ALL=C $(LINK) $(RIOTTOOLS)/testprogs/minimal_linkable.c -o /dev/null -lc -Wall -Wextra -pedantic -z noexecstack 2> /dev/null && echo 1 || echo 0)
PROBE_LINK_NOWARNRWX = $(shell LC_ALL=C $(LINK) $(RIOTTOOLS)/testprogs/minimal_linkable.c -o /dev/null -lc -Wall -Wextra -pedantic -Wl,--no-warn-rwx-segments 2> /dev/null && echo 1 || echo 0)

# makefiles/libc/newlib.mk: nano.specs and the include directories of newlib
PROBE_LINK_NANO_SPECS = $(shell $(LINK) -specs=nano.specs -E - 2>/dev/null >/dev/null </dev/null ; echo $$?)
PROBE_LINK_NANO_WCHAR_WARNING = $(shell LC_ALL=C $(LINK) $(RIOTTOOLS)/testprogs/minimal_linkable.c -o /dev/null -lc -specs=nano.specs -Wall -Wextra -pedantic 2>&1 | grep -q "use of wchar_t values across objects may fail" ; echo $$?)
# Search for newlib.h: in the standard search path of the compiler, then in
# NEWLIB_INCLUDE_PATTERNS (makefiles/libc/newlib.mk), then next to the
# cross gcc on PATH. `realpath` (not `abspath`) supports Mingw32.
COMPILER_INCLUDE_PATHS = $(shell $(PREFIX)gcc -v -x c -E /dev/null 2>&1 | \
                              sed \
                              -e '1,/\#include <...> search starts here:/d' \
                              -e '/End of search list./,$$d' \
                              -e 's/^ *//')
PROBE_NEWLIB_INCLUDE_DIR = $(or \
  $(firstword $(realpath $(dir $(wildcard $(addsuffix /newlib.h, $(COMPILER_INCLUDE_PATHS)))))), \
  $(firstword $(realpath $(dir $(wildcard $(addsuffix /newlib.h, $(NEWLIB_INCLUDE_PATTERNS)))))), \
  $(realpath $(wildcard $(dir $(shell command -v $(PREFIX)gcc 2>/dev/null))/../$(TARGET_ARCH)/include)))
PROBE_NEWLIB_NANO_INCLUDE_DIR = $(firstword $(wildcard $(NEWLIB_INCLUDE_DIR)/newlib-nano \
                                                      $(NEWLIB_INCLUDE_DIR)/newlib/nano \
                                                      $(NEWLIB_INCLUDE_DIR)/nano))

# makefiles/git_version.inc.mk: git description and branch of RIOTBASE
PROBE_GIT_DESCRIBE = $(call memoized,PROBE_GIT_DESCRIBE,$(shell git --git-dir="$(RIOTBASE)/.git" describe --always --abbrev=4 2> /dev/null))
PROBE_GIT_BRANCH = $(call memoized,PROBE_GIT_BRANCH,$(shell git --git-dir="$(RIOTBASE)/.git" rev-parse --abbrev-ref HEAD))

# Makefile.include: the version tuple of RIOT_VERSION, else of RIOT_DUMMY_VERSION
BUILD_RIOT_VERSION_TUPLE = $(or $(call version_tuple,$(RIOT_VERSION)),$(call version_tuple,$(RIOT_DUMMY_VERSION)))
# makefiles/modules.inc.mk: -DMODULE_<NAME> of every module and package
BUILD_EXTDEFINES = $(EXTDEFINES)
