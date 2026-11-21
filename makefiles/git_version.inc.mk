# Generated from git_version.build.yaml by dist/tools/config_data/config_data.py.
# Do not edit: change git_version.build.yaml and run `just generate-config-data`.

# GIT_VERSION is git description + branch name if it not master
# Empty when not in a git repository
#
#   2019.10-devel-97-g3bcc72
#   2019.10-devel-97-g3bcc72-pr/git_version

GIT_DESCRIBE = $(PROBE_GIT_DESCRIBE)
GIT_BRANCH = $(PROBE_GIT_BRANCH)

# the branch without a trailing `master` (Make: $(GIT_BRANCH:master=)),
# then with a leading dash: nothing on master
BUILD_GIT_BRANCH_STEM = $(patsubst %master,%,$(GIT_BRANCH))
BUILD_GIT_BRANCH_SUFFIX = $(patsubst %,-%,$(BUILD_GIT_BRANCH_STEM))
_GIT_VERSION = $(GIT_DESCRIBE)$(BUILD_GIT_BRANCH_SUFFIX)
GIT_VERSION ?= $(if $(GIT_DESCRIBE),$(_GIT_VERSION))

# This variable is recursively expanded on purpose. It is only expanded when
# $(RIOT_VERSION) has not been set already. For CI builds, Makefile.include
# sets the version to 'buildtest' before this is used, so $(GIT_VERSION) is
# never expanded and two shell calls are saved. Outside of CI, $(GIT_VERSION)
# is memoized and will not be re-evaluated on every expansion.
RIOT_VERSION_GIT = $(if $(GIT_VERSION),$(GIT_VERSION),'UNKNOWN (builddir: $(RIOTBASE))')
