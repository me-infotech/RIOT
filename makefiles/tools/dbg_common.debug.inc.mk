# Generated from dbg_common.debug.yaml by dist/tools/term/term.py.
# Do not edit: change dbg_common.debug.yaml and run `just generate-term-data`.

# Control whether to use PyCortexMDebug
USE_PYCORTEXMDEBUG ?= 0

ifeq ($(USE_PYCORTEXMDEBUG),1)
  DEBUGDEPS += $(RIOTTOOLS)/PyCortexMDebug/checkout
  DBG_EXTRA_FLAGS += --init-command='$(RIOTTOOLS)/PyCortexMDebug/checkout/scripts/gdb.py'
  ifneq (,$(SVD_MODEL))
    DBG_EXTRA_FLAGS += --eval-command='svd_load $(SVD_VENDOR) $(SVD_MODEL)'
  endif
endif

# Add RIOT_BASE to the list of directories to search for source code in
DBG_EXTRA_FLAGS += --eval-command='directory $(RIOTBASE)'
