# Default when RIOTBASE is not set and is executed from the RIOT directory
RIOTBOARD ?= $(or $(RIOTBASE),$(CURDIR))/boards
BOARDSDIRS ?= $(EXTERNAL_BOARD_DIRS) $(RIOTBOARD)

# List all boards in a directory
# By default, all directories in board directory except 'common'
#   use 'wildcard */.' to only list directories
_get_boards_in_directory = $(filter-out common,$(patsubst $1/%/.,%,$(wildcard $1/*/.)))

# Use `:=` so that it is evaluated before BOARDSDIRS gets eventually changed
ALLBOARDS := $(sort \
                    $(foreach dir,\
                              $(BOARDSDIRS),\
                              $(call _get_boards_in_directory,$(dir))))

# Set the default value from `BOARDS`
BOARDS ?= $(ALLBOARDS)

# `info-boards` and `info-emulated-boards` are just recipes
# (just/repository.just); the variables above stay for the Make targets of
# groups 2A/2B/2C/3.
