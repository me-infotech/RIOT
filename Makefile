.all:

.PHONY: all docclean

all:
	$(call just_hint)
	@exit 1

doc-ci:
	@./dist/tools/features_yaml2mx/features_yaml2mx.py \
		features.yaml \
		--output-md doc/doxygen/src/feature_list.md
	"$(MAKE)" -C doc/doxygen $@

docclean:
	"$(MAKE)" -BC doc/doxygen clean
	"$(MAKE)" -C doc/starlight clean

pkg-clean:
	@echo "Cleaning all package sources"
	rm -rf build/pkg

include makefiles/boards.inc.mk
include makefiles/app_dirs.inc.mk

-include makefiles/tests.inc.mk

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

# The repository commands of the base directory (welcome, doc, info-boards,
# generate-*, print-versions, ...) are no longer Make targets; they run with
# just (root justfile). Make points there.
define just_hint
	@echo "The repository commands of the RIOT base directory run with just:"
	@echo "    just --list"
	@echo "Applications are still built with make in their directory, e.g.:"
	@echo "    cd examples/basic/default"
	@echo "    make BOARD=<INSERT_BOARD_NAME>"
endef

.DEFAULT:
	@echo '*** ERROR: unrecognized target "$@"'
	@echo ""
	$(call just_hint)
	@exit 1
