# Generated from flash.yaml by dist/tools/flash/flash.py.
# Do not edit: change flash.yaml and run `just generate-flash-data`.

# Set the target for the JLink programmer for flashing, JLINK expects an
# underscore in the target, like "nrf52832_xxaa".
# Boards that do not use a JLink ignore the flag.
JLINK_DEVICE = $(subst xx,_xx,$(CPU_MODEL))
