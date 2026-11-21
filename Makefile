.all:

.PHONY: all doc-man doc-latex doc-ci docclean doc-starlight welcome

all: welcome
	@echo ""
	@exit 1

# `doc` moved to just (`just doc`). The formats still built with Make reuse
# its steps: Make may call just, a just recipe never calls make.
JUST ?= just

doc-man doc-latex:
	@"$(JUST)" --justfile "$(CURDIR)/justfile" _doc-feature-list
	"$(MAKE)" -C doc/doxygen $@

# doc/doxygen downloads the required Doxygen and runs `just doc` with it.
doc-ci:
	"$(MAKE)" -C doc/doxygen $@

doc-starlight:
	"$(MAKE)" -C doc/starlight dev

docclean:
	"$(MAKE)" -BC doc/doxygen clean
	"$(MAKE)" -C doc/starlight clean

# Directory of this Makefile (with a trailing slash), also with `make -f`:
# `distclean` finds the justfile there.
_riot_root := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

include makefiles/boards.inc.mk
include makefiles/app_dirs.inc.mk

include makefiles/tools/riotgen.inc.mk
-include makefiles/tests.inc.mk

include makefiles/color.inc.mk

CLEAN_DIRS := $(APPLICATION_DIRS) $(TOOLS_DIRS)

.PHONY: clean distclean $(CLEAN_DIRS:%=CLEAN--%) $(CLEAN_DIRS:%=DISTCLEAN--%)
clean: $(CLEAN_DIRS:%=CLEAN--%)
	@echo "Cleaned all build products."

distclean: docclean _pkg-clean $(CLEAN_DIRS:%=DISTCLEAN--%)
	@echo "Cleaned everything."

$(CLEAN_DIRS:%=CLEAN--%):
	-"$(MAKE)" -C $(@:CLEAN--%=%) clean

$(CLEAN_DIRS:%=DISTCLEAN--%):
	-"$(MAKE)" -C $(@:DISTCLEAN--%=%) distclean

# Prints a welcome message
define welcome_message
	@echo "Welcome to RIOT - The friendly OS for IoT!"
	@echo ""
	@echo "You executed 'make' from the base directory."
	@echo "Usually, you should run 'make' in your application's directory instead."
	@echo ""
	@echo "Please see our Quick Start Guide at:"
	@echo "    https://guide.riot-os.org/getting-started/installing/"
	@echo "You can ask questions or discuss with other users on our forum:"
	@echo "    https://forum.riot-os.org"
	@echo ""
	@echo "Available targets for the RIOT base directory include:"
	@echo " generate-{board,driver,example,module,pkg,test}"
	@echo " info-{applications,boards,emulated-boards} info-applications-supported-boards"
	@echo " clean distclean docclean"
	@echo " doc-{starlight,man,latex,ci}"
	@echo ""
	@echo "Repository commands that moved to just (run 'just --list'):"
	@echo " doc generate-features pkg-clean print-versions"
	@echo ""
	@echo "==> tl;dr Try running:"
	@echo "    cd examples/basic/default"
	@echo "    make BOARD=<INSERT_BOARD_NAME>"
endef

welcome:
	$(call welcome_message)

# `doc` moved to just, but it is also the name of the documentation directory:
# without this rule Make would report the existing directory as up to date.
.PHONY: doc
.DEFAULT doc:
	@echo '*** ERROR: unrecognized target "$@"'
	@echo ""
	$(call welcome_message)
	@exit 1

# Prerequisite of `distclean` (kept at the end, so that Make's messages keep
# their line numbers). `pkg-clean` moved to just (`just pkg-clean`);
# `distclean` runs its steps (`_pkg-clean` in the justfile next to this
# Makefile) at the place of the former prerequisite, so the cleaning exists
# only in the justfile (Make may call just, a just recipe never calls make).
# As before, they act in CURDIR, and Make's options keep their effect: with
# -s the command line is hidden; with -n just only prints the commands
# (dry-run) and Make shows them in place of the recipe, changing nothing.
_pkg_clean_flags = $(firstword -$(MAKEFLAGS))
_pkg_clean_mode = $(strip \
  $(if $(findstring n,$(_pkg_clean_flags)),dry-run,\
  $(if $(findstring s,$(_pkg_clean_flags)),silent,echo)))
_pkg_clean_run = "$(JUST)" --justfile "$(_riot_root)justfile" _pkg-clean "$(CURDIR)" $(_pkg_clean_mode)
_pkg_clean_dry_run = $(if $(filter dry-run,$(_pkg_clean_mode)),$(shell $(_pkg_clean_run) | sed -n $(1)p))
.PHONY: _pkg-clean
_pkg-clean:
	$(if $(filter dry-run,$(_pkg_clean_mode)),$(call _pkg_clean_dry_run,1),@$(_pkg_clean_run))
	$(call _pkg_clean_dry_run,2)
