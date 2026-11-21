# Generated from default-radio-settings.build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change default-radio-settings.build.yaml and run `just generate-config-data`.

# Set a custom channel if needed
ifndef CONFIG_KCONFIG_MODULE_IEEE802154
  ifneq (,$(DEFAULT_CHANNEL))
    # radio is cc110x sub-GHz
    ifneq (,$(filter cc110x,$(USEMODULE)))
      CFLAGS += -DCONFIG_CC110X_DEFAULT_CHANNEL=$(DEFAULT_CHANNEL)
    endif
    # radio is IEEE 802.15.4 sub-GHz, else 2.4 GHz
    ifneq (,$(filter at86rf212b,$(USEMODULE)))
      CFLAGS += -DCONFIG_IEEE802154_DEFAULT_SUBGHZ_CHANNEL=$(DEFAULT_CHANNEL)
    else
      CFLAGS += -DCONFIG_IEEE802154_DEFAULT_CHANNEL=$(DEFAULT_CHANNEL)
    endif
  endif
  # Set a custom PAN ID if needed
  ifneq (,$(DEFAULT_PAN_ID))
    CFLAGS += -DCONFIG_IEEE802154_DEFAULT_PANID=$(DEFAULT_PAN_ID)
  endif
endif
