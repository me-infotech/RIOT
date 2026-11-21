# The files of the distribution besides the application's DIST_FILES are
# distribution data: makefiles/bindist.dist.yaml. The file included here is
# generated from it (`just generate-dist-data`); edit the YAML, not it.
include $(RIOTMAKE)/bindist.dist.inc.mk

# Avoid including APPLICATION_MODULE twice to prevent multiple definition errors
USEMODULE += $(filter-out $(APPLICATION_MODULE),$(BIN_USEMODULE))

# The directories of the binary modules are build data:
# makefiles/bindist.build.yaml. The file included here is generated from it
# (`just generate-config-data`); edit the YAML, not it.
include $(RIOTMAKE)/bindist.build.mk

bindist: all
	@mkdir -p bindist
	@for i in $(DIST_FILES) ; do \
		echo Copying $$i to bindist. ; \
		cp -a --parents $$i bindist ; \
		done
	@cp -a bin/$(BOARD)/$(APPLICATION).bin bindist

	@echo "BINDIST_RIOT_VERSION=$(RIOT_VERSION)" > bindist/Makefile.distcheck
	@echo "BINDIST_GIT_HEAD=$$(git -C $(RIOTBASE) describe)" >> bindist/Makefile.distcheck

prepare_check_bindist:
	@[ "$(BINDIST_RIOT_VERSION)" = "$(RIOT_VERSION)" ] || \
		echo "Warning! RIOT_VERSION doesn't match!"
	@[ "$(BINDIST_GIT_HEAD)" = "$$(git -C $(RIOTBASE) describe)" ] || \
		echo "Warning! git describe doesn't match!"

check_bindist: prepare_check_bindist all
	@test $(shell md5sum bin/$(BOARD)/$(APPLICATION).bin | cut -f1 -d\ ) \
		= $(shell md5sum $(APPLICATION).bin | cut -f1 -d\ ) \
		&& echo "bin/$(BOARD)/$(APPLICATION).bin matches $(APPLICATION).bin." \
		|| echo "bin/$(BOARD)/$(APPLICATION).bin and $(APPLICATION).bin don't match!"
