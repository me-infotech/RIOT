# The tools and flags of the GNU toolchain are build data:
# makefiles/toolchain/gnu.build.yaml. The file included here is generated
# from it (`just generate-config-data`); edit the YAML, not it.
include $(RIOTMAKE)/toolchain/gnu.build.mk

# We use GDB for debugging (includes makefiles/tools/gdb.inc.mk): generated
# from gnu.debug.yaml (step G2B-1)
include $(RIOTMAKE)/toolchain/gnu.debug.inc.mk

# this needs to be recursively evaluated
RCFLAGS_WRITE_SARIF = -fdiagnostics-add-output=sarif:file='$$@.sarif'
