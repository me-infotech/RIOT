# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# RIOT task layer: commands that need no build system, moved from GNU Make
# to just (see dist/tools/task_layer/README.md). just finds this file from any
# directory of the repository; whether a recipe may run everywhere is checked
# per target (rule R6).
#
# Rules: a recipe never calls make; inputs are repository files and host
# tools only; the commands are no longer Make targets. Applications are still
# built with make in their directory. Tested with just 1.59.0.

# Recipe lines run with /bin/sh, as GNU Make ran them.
set shell := ["/bin/sh", "-c"]

# Doxygen binary and tag file of the API documentation; like `DOXYGEN ?=` and
# `TAGFILE ?=` in Make they come from the environment or the command line
# (`just DOXYGEN=/path/to/doxygen doc`).
DOXYGEN := env("DOXYGEN", "doxygen")
TAGFILE := env("TAGFILE", "html/riot.tag")

# Oldest recommended Doxygen version. doc/doxygen/Makefile reads this line for
# `make doc-ci`; update DOXYGEN_TGZ_SHA512 there when changing it.
doxygen_min_version := "1.15.0"

# List the recipes.
[private]
default:
    @{{ quote(just_executable()) }} --justfile {{ quote(justfile()) }} --list

# Print the versions of the host toolchains.
print-versions:
    @./dist/tools/ci/print_toolchain_versions.sh

# Regenerate makefiles/features_existing.inc.mk from features.yaml.
generate-features:
    @./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml --output-makefile makefiles/features_existing.inc.mk

# Generate the HTML API documentation in doc/doxygen/html.
[working-directory: 'doc/doxygen']
doc: _doc-feature-list _doc-graphviz-check _doc-changelog && _doc-doxygen-version
    ( cat riot.doxyfile ; echo "GENERATE_HTML = yes" ; \
      echo "GENERATE_TAGFILE = {{ TAGFILE }}" ) | {{ DOXYGEN }} -
    @echo ""
    @echo "RIOT documentation successfully generated at file://{{ justfile_directory() }}/doc/doxygen/html/index.html"

# The private recipes below are the steps of `doc`. `make doc-man`,
# `make doc-latex` and `make doc-ci` (still in Make) run them as well, so each
# step exists only once.

# Feature list page, generated from features.yaml.
[private]
_doc-feature-list:
    @./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml --output-md doc/doxygen/src/feature_list.md

# GraphViz is a mandatory dependency to generate the Doxygen documentation.
[private]
_doc-graphviz-check:
    #!/bin/sh
    red= reset= echo='/usr/bin/env echo'
    if [ "${CC_NOCOLOR:-}" != 1 ] && [ -t 1 ] && [ -t 2 ]; then
        red='\033[1;31m' reset='\033[0m' echo='/usr/bin/env echo -e'
    fi
    command -v dot >/dev/null 2>&1 || {
        $echo "${red}Error: GraphViz (dot) is not installed." \
            "GraphViz is mandatory to generate the RIOT documentation.${reset}"
        exit 1
    }

# Changelog page, generated from release-notes.txt.
[private]
[working-directory: 'doc/doxygen']
_doc-changelog:
    @./generate-changelog.py src/changelog.md.tmp ../../release-notes.txt src/changelog.md

# Warn if Doxygen is older than doxygen_min_version (output may be wrong).
[private]
_doc-doxygen-version:
    #!/bin/sh
    red= reset= echo='/usr/bin/env echo'
    if [ "${CC_NOCOLOR:-}" != 1 ] && [ -t 1 ] && [ -t 2 ]; then
        red='\033[1;31m' reset='\033[0m' echo='/usr/bin/env echo -e'
    fi
    min={{ quote(doxygen_min_version) }}
    cur=$({{ DOXYGEN }} --version | cut -d ' ' -f1)
    if [ "$({ echo "$min"; echo "$cur"; } | sort -V | head -n1)" != "$min" ]; then
        $echo "${red}Warning: Doxygen version $cur is too old." \
            "It is recommended to use at least version $min" \
            "to avoid incorrectly formatted output.\nYou can use 'make doc-ci' to build" \
            "the documentation with the required Doxygen version, which will be downloaded" \
            "and (if required) compiled locally.${reset}"
    fi

# Moved from Makefile.include (application level). Runs in the calling
# directory, without arguments and with the absolute path, as Make did.
# List the serial TTYs connected to this host.
[no-cd]
list-ttys:
    @{{ justfile_directory() }}/dist/tools/usb-serial/ttys.py
