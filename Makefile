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

pkg-clean:
	@echo "Cleaning all package sources"
	rm -rf build/pkg

include makefiles/boards.inc.mk
include makefiles/app_dirs.inc.mk

include makefiles/tools/riotgen.inc.mk
-include makefiles/tests.inc.mk

include makefiles/color.inc.mk

CLEAN_DIRS := $(APPLICATION_DIRS) $(TOOLS_DIRS)

.PHONY: clean distclean $(CLEAN_DIRS:%=CLEAN--%) $(CLEAN_DIRS:%=DISTCLEAN--%)
clean: $(CLEAN_DIRS:%=CLEAN--%)
	@echo "Cleaned all build products."

distclean: docclean pkg-clean $(CLEAN_DIRS:%=DISTCLEAN--%)
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
	@echo " clean distclean docclean pkg-clean"
	@echo " doc-{starlight,man,latex,ci}"
	@echo ""
	@echo "Repository commands that moved to just (run 'just --list'):"
	@echo " doc generate-features print-versions"
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
