# Generated from bindist.dist.yaml by dist/tools/bindist/bindist.py.
# Do not edit: change bindist.dist.yaml and run `just generate-dist-data`.

# the objects of the binary modules, where Make's recipe finds them
# (bin/<BOARD>: Make's default BINDIR, relative to the application)
DIST_FILES += $(patsubst %,bin/$(BOARD)/%/*.o,$(BIN_USEMODULE))
