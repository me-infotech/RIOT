# Generated from pkg.build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change pkg.build.yaml and run `just generate-config-data`.
# The build part of pkg/pkg.mk, which includes this file once per
# section with RIOT_BUILD_SECTION set to the name of the section.

ifeq (checks,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  ifeq ($(PKG_NAME),)
    $(error PKG_NAME not defined)
  endif
  ifeq ($(PKG_URL),)
    $(error PKG_URL not defined)
  endif
  ifeq ($(PKG_VERSION),)
    $(error PKG_VERSION not defined)
  endif
  ifeq ($(PKG_LICENSE),)
    $(error PKG_LICENSE not defined)
  endif
  ifneq (,$(PKG_MIRROR_URL))
    ifneq ($(PKG_USE_MIRROR),0)
      PKG_URL = $(PKG_MIRROR_URL)
    endif
  endif
  PKG_DIR ?= $(CURDIR)
  PKG_PATCH_DIR ?= $(PKG_DIR)/patches
  PKG_BUILD_OUT_OF_SOURCE ?= 1
  ifeq ($(PKG_BUILD_OUT_OF_SOURCE),1)
    PKG_SOURCE_DIR ?= $(PKGDIRBASE)/$(PKG_NAME)
    PKG_BUILD_DIR ?= $(BINDIR)/pkg-build/$(PKG_NAME)
  else
    # in-source builds: packages are cloned within the application build
    # directory in a separate pkg tree
    PKG_SOURCE_DIR ?= $(BINDIR)/pkg/$(PKG_NAME)
    PKG_BUILD_DIR = $(PKG_SOURCE_DIR)
  endif
  # If CARGO_HOME is set, use it to search for `git-cache-rs` (git-cache),
  # otherwise try the local default directory. The git-cache can also be set
  # directly with GIT_CACHE_RS.
  CARGO_HOME ?= $(HOME)/.cargo
endif

# without PKG_SOURCE_LOCAL
ifeq (git,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  ifeq ($(QUIET),1)
    GIT_QUIET ?= --quiet
  endif
  GITFLAGS ?= -c user.email=buildsystem@riot -c user.name="RIOT buildsystem"
  ifeq (,$(GITAMFLAGS))
    # These flags will be amended to the `git am` command after the deprecation
    # period has ended.
    GITAMFLAGS ?= $(GIT_QUIET)
    GITAMFLAGS += --no-gpg-sign --ignore-whitespace --whitespace=nowarn
  endif
  PKG_PATCHES = $(sort $(wildcard $(PKG_PATCH_DIR)/*.patch))
endif

ifeq (flags,$(RIOT_BUILD_SECTION))
  RIOT_BUILD_SECTION :=
  # Disabling some diagnostics: These issues needs to be fixed upstream
  CFLAGS += -Wno-maybe-uninitialized
  ifeq ($(TOOLCHAIN),llvm)
    CFLAGS += -Wno-documentation
  endif
  # Disabling -Wunterminated-string-initialization on toolchains that support this
  # warning
  ifeq (1,$(call version_is_greater_or_equal,$(GCC_VERSION),15))
    CFLAGS += -Wno-unterminated-string-initialization
    # this flag should not be passed to g++, only gcc:
    CXXUWFLAGS += -Wno-unterminated-string-initialization
  endif
endif

ifneq (,$(RIOT_BUILD_SECTION))
  $(error pkg/pkg.mk: no build section $(RIOT_BUILD_SECTION))
endif
