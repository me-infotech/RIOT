# Root justfile, located relative to this file. The Doxygen targets (doc,
# doc-man, doc-latex, html, man, latex, check, doxygen-version,
# graphviz-check) are just recipes (just/doc.just); only `doc-ci`, the CSS
# rules and `clean` remain here.
_RIOT_JUSTFILE := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../justfile)

RIOTBASE  ?= $(shell git rev-parse --show-toplevel)
RIOTTOOLS ?= $(RIOTBASE)/dist/tools

# use lessc (http://lesscss.org/#using-less) for compiling CSS
# It can also be installed in ubuntu with the `node-less` package
LESSC ?= lessc

# Check that the doxygen version is not too old to avoid
# certain bugs that were fixed in later revisions. Especially
# Debian-based distributions tend to have very old versions.
# When updating the version, make sure to update the SHA512 checksum
# of the doxygen-x.xx.x.linux.bin.tar.gz archive accordingly to avoid cache
# misses. Single source: just/settings.just.
DOXYGEN_MIN_VERSION := $(shell just --justfile "$(_RIOT_JUSTFILE)" --evaluate DOXYGEN_MIN_VERSION 2>/dev/null)
ifneq (,$(filter doc-ci,$(MAKECMDGOALS)))
  ifeq (,$(DOXYGEN_MIN_VERSION))
    $(error DOXYGEN_MIN_VERSION could not be read from just/settings.just (is just installed))
  endif
endif
DOXYGEN_TGZ_SHA512 = 0e99fb9a65f9fada2fe90ea0d1f940b8e58d62801f880614b440b9f3a9f82a5c1a8dd1d0719ee6a46f9612ea7447655d5c8494f63463fe7f1222987bdb1485a9

# for the `doc-ci` target, we can choose which Doxygen version should be built.
# If nothing has been chosen, select the minimum version.
# Valid options are `latest` and version numbers such as `1.13.2`.
DOXYGEN_VERSION ?= $(DOXYGEN_MIN_VERSION)

# If we don't build the Doxygen version specified here, remove the SHA512 sum
# to avoid a checksum error from `dist/tools/dlcache.sh`
ifneq ($(DOXYGEN_VERSION),$(DOXYGEN_MIN_VERSION))
  DOXYGEN_TGZ_SHA512=
endif

.NOTPARALLEL:

.PHONY: doc-ci
doc-ci: $(RIOTTOOLS)/doxygen/Makefile
	@PKG_VERSION=$(DOXYGEN_VERSION) PKG_SHA512=$(DOXYGEN_TGZ_SHA512) $(MAKE) -C $(RIOTTOOLS)/doxygen all --no-print-directory
	@DOXYGEN=$(RIOTTOOLS)/doxygen/doxygen just --justfile "$(_RIOT_JUSTFILE)" \
		$(if $(filter command line,$(origin DOCUMENTATION_FORMAT)),DOCUMENTATION_FORMAT='$(subst ','\'',$(DOCUMENTATION_FORMAT))') \
		doxygen-doc

src/css/riot.css: src/css/riot.less src/css/variables.less
	@$(LESSC) $< $@

src/css/variables.less: src/config.json
	@grep "^\s*\"@" $< | sed -e 's/^\s*"//g' -e 's/":\s*"/: /g' \
	  -e 's/",\?$$/;/g' -e 's/\\"/"/g' > $@

clean:
	-@rm -rf latex man html doxygen_objdb_*.tmp doxygen_entrydb_*.tmp src/changelog.md
	@$(MAKE) -C $(RIOTTOOLS)/doxygen clean
