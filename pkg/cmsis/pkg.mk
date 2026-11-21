# Generated from pkg.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change pkg.yaml and run `just generate-config-data`.
# The build part of pkg/cmsis/Makefile, which includes this file.

PKG_NAME = cmsis
PKG_URL = https://github.com/ARM-software/CMSIS_5

PKG_VERSION = 2b7495b8535bdcb306dac29b9ded4cfb679d7e5c  # 5.9.0
PKG_LICENSE = Apache-2.0
CMSIS_NN_MODULES = cmsis-nn_activationfunctions cmsis-nn_convolutionfunctions cmsis-nn_fullyconnectedfunctions cmsis-nn_nnsupportfunctions cmsis-nn_poolingfunctions cmsis-nn_softmaxfunctions
CMSIS_DSP_MODULES = cmsis-dsp_basicmathfunctions cmsis-dsp_commontables cmsis-dsp_complexmathfunctions cmsis-dsp_controllerfunctions cmsis-dsp_fastmathfunctions cmsis-dsp_filteringfunctions cmsis-dsp_matrixfunctions cmsis-dsp_statisticsfunctions cmsis-dsp_supportfunctions cmsis-dsp_transformfunctions
CMSIS_DSP_MODULES_USED = $(filter $(CMSIS_DSP_MODULES),$(USEMODULE))
CMSIS_NN_MODULES_USED = $(filter $(CMSIS_NN_MODULES),$(USEMODULE))
CMSIS_MODULES_USED = $(CMSIS_DSP_MODULES_USED) $(CMSIS_NN_MODULES_USED)
PKG_SPARSE_PATHS = CMSIS/Core/Include

ifneq (,$(CMSIS_NN_MODULES_USED))
  PKG_SPARSE_PATHS += CMSIS/NN
  CMSIS_DSP_NEEDED = 1
endif

ifneq (,$(CMSIS_DSP_MODULES_USED)$(CMSIS_DSP_NEEDED))
  PKG_SPARSE_PATHS += CMSIS/DSP
endif

include $(RIOTBASE)/pkg/pkg.mk
CFLAGS += -Wno-cast-align
