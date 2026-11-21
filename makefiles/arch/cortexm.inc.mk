# The build flags, the linker script and the toolchain prefix of Cortex-M are
# build data: makefiles/arch/cortexm.build.yaml. The file included here is
# generated from it (`just generate-config-data`); edit the YAML, not it.
include $(RIOTMAKE)/arch/cortexm.build.mk

# Avoid overriding the default rule:
all:

# Rule to generate assembly listings from ELF files:
%.lst: %.elf
	$(OBJDUMP) $(OBJDUMPFLAGS) $< > $@
