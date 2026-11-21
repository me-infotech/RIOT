# Name, URL, version, sparse paths and flags of the package are package
# data: pkg/cmsis/pkg.yaml. The file included here is generated from it
# (`just generate-config-data`); it includes pkg/pkg.mk.
include $(RIOTBASE)/pkg/cmsis/pkg.mk

DIR_activationfunctions        := ActivationFunctions
DIR_convolutionfunctions       := ConvolutionFunctions
DIR_fullyconnectedfunctions    := FullyConnectedFunctions
DIR_nnsupportfunctions         := NNSupportFunctions
DIR_poolingfunctions           := PoolingFunctions
DIR_softmaxfunctions           := SoftmaxFunctions

DIR_basicmathfunctions      := BasicMathFunctions
DIR_commontables            := CommonTables
DIR_complexmathfunctions    := ComplexMathFunctions
DIR_controllerfunctions     := ControllerFunctions
DIR_fastmathfunctions       := FastMathFunctions
DIR_filteringfunctions      := FilteringFunctions
DIR_matrixfunctions         := MatrixFunctions
DIR_statisticsfunctions     := StatisticsFunctions
DIR_supportfunctions        := SupportFunctions
DIR_transformfunctions      := TransformFunctions

.PHONY: cmsis-dsp_% cmsis-nn_%

all: $(CMSIS_MODULES_USED)

cmsis-dsp_%:
	$(QQ)"$(MAKE)" -C $(PKG_SOURCE_DIR)/CMSIS/DSP/Source/$(DIR_$*) -f $(CURDIR)/Makefile.cmsis-dsp MODULE=$@

cmsis-nn_%:
	$(QQ)"$(MAKE)" -C $(PKG_SOURCE_DIR)/CMSIS/NN/Source/$(DIR_$*) -f $(CURDIR)/Makefile.cmsis-nn MODULE=$@
