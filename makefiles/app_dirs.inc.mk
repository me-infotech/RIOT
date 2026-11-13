# Root justfile, located relative to this file.
_RIOT_JUSTFILE := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../justfile)

.PHONY: info-applications-supported-boards

# fallback so empty RIOTBASE won't lead to "/examples/"
RIOTBASE ?= .

# Single source: just/settings.just (`info-applications` is a just recipe).
# Only the goals below need it; without just the other root goals still work.
APPS_BASE_DIRS := $(shell just --justfile "$(_RIOT_JUSTFILE)" --evaluate APPS_BASE_DIRS 2>/dev/null)
ifeq (,$(APPS_BASE_DIRS))
  ifneq (,$(filter clean distclean info-applications-supported-boards CLEAN--% DISTCLEAN--%,$(MAKECMDGOALS)))
    $(error APPS_BASE_DIRS could not be read from just/settings.just (is just installed))
  endif
endif
TOOLS_BASE_DIRS = dist/tools

# The same derivation is the just recipe `info-applications`
# (just/repository.just); keep both alike.
# 1. recursively find Makefiles
# 2. take parent folders
# 3. exclude build artifacts (below bin/)
# 4. exclude false positives from app_dirs.blacklist
# 5. sort
APPLICATION_DIRS := $(if $(APPS_BASE_DIRS),$(shell find $(APPS_BASE_DIRS) -name Makefile -type f | \
    xargs dirname | \
    grep -vF "/bin/" | \
    grep -vFf $(RIOTBASE)/makefiles/app_dirs.blacklist | \
    sort | uniq))

# used for `make claen` and `make distclean`
TOOLS_DIRS := $(shell find $(TOOLS_BASE_DIRS) -mindepth 2 -maxdepth 2 -name Makefile -type f | \
    xargs dirname | \
    grep -vFf $(RIOTBASE)/makefiles/app_dirs.blacklist | \
    sort | uniq)

# All applications / board output of `info-boards-supported`.
info-applications-supported-boards:
	@for dir in $(APPLICATION_DIRS); do \
	  $(MAKE) --no-print-directory -C $${dir} info-boards-supported -j 2>/dev/null | xargs -n 1 echo $${dir}; \
	done
# BOARDS values from 'boards.inc.mk' to only evaluate it once
info-applications-supported-boards: export BOARDS ?=
