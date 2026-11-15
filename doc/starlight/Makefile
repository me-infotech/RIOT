# Root justfile, located relative to this file. The Starlight targets
# (build, preview, dev, integrate_outside_files and the copy targets) are just
# recipes (`just starlight-<target>`, just/doc.just).
_RIOT_JUSTFILE := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../../justfile)

# Not one of the migrated targets (the name `install` is group 2C in the
# target inventory); its steps are the just recipe `starlight-install`.
.PHONY: install
install:
	@just --justfile "$(_RIOT_JUSTFILE)" starlight-install

.PHONY: test
test: install
	@npm test --prefix $(CURDIR)

.PHONY: clean
clean:
	-@rm -rf node_modules .astro dist
