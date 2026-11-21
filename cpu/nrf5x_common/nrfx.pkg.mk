# Generated from nrfx.pkg.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change nrfx.pkg.yaml and run `just generate-config-data`.
# The build part of cpu/nrf5x_common/Makefile.nrfx, which includes this file.

PKG_NAME = nrf5x_nrfx_mdk
PKG_URL = https://github.com/NordicSemiconductor/nrfx

# Release 3.14.0
PKG_VERSION = 11f57e578c7feea13f21c79ea0efab2630ac68c7
PKG_LICENSE = BSD-3-Clause

# CPU Family specific vendor header files using sparse checkout, since the
# repository is multiple 100MBs big.
ifeq ($(CPU_FAM),nrf51)
  PKG_SPARSE_PATHS = mdk/nrf51.h
  PKG_SPARSE_PATHS += mdk/nrf51_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf51822_peripherals.h
else ifeq ($(CPU_FAM),nrf52)
  PKG_SPARSE_PATHS = mdk/nrf52.h
  PKG_SPARSE_PATHS += mdk/nrf52_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf52810.h
  PKG_SPARSE_PATHS += mdk/nrf52810_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf52810_name_change.h
  PKG_SPARSE_PATHS += mdk/nrf52810_peripherals.h
  PKG_SPARSE_PATHS += mdk/nrf52811.h
  PKG_SPARSE_PATHS += mdk/nrf52811_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf52811_peripherals.h
  PKG_SPARSE_PATHS += mdk/nrf52832_peripherals.h
  PKG_SPARSE_PATHS += mdk/nrf52833.h
  PKG_SPARSE_PATHS += mdk/nrf52833_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf52833_peripherals.h
  PKG_SPARSE_PATHS += mdk/nrf52840.h
  PKG_SPARSE_PATHS += mdk/nrf52840_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf52840_name_change.h
  PKG_SPARSE_PATHS += mdk/nrf52840_peripherals.h
else
  # Makefile.nrfx: `else ifneq (nrf53%, $(CPU_FAM))` compares with the
  # literal text `nrf53%`, so it holds for every CPU family
  PKG_SPARSE_PATHS += mdk/nrf5340_application.h
  PKG_SPARSE_PATHS += mdk/nrf5340_application_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf5340_application_name_change.h
  PKG_SPARSE_PATHS += mdk/nrf5340_application_peripherals.h
  PKG_SPARSE_PATHS += mdk/nrf5340_network.h
  PKG_SPARSE_PATHS += mdk/nrf5340_network_bitfields.h
  PKG_SPARSE_PATHS += mdk/nrf5340_network_name_change.h
  PKG_SPARSE_PATHS += mdk/nrf5340_network_peripherals.h
endif

# Since we do not want to pull all the vendor headers for all CPU families,
# we create a separate subdirectory for each one. That assures that it will
# be patched correctly every time, otherwise the files fetched on the second
# run will not be patched.
PKG_SOURCE_DIR = $(BUILD_DIR)/nrf5x_nrfx_mdk/$(CPU_FAM)
PKG_PATCH_DIR = $(RIOTCPU)/nrf5x_common/include/vendor/patches
VENDOR_FOLDER = $(PKG_SOURCE_DIR)/vendor
include $(RIOTBASE)/pkg/pkg.mk
