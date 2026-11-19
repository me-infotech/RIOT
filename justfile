# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# RIOT task layer, minimal proof of concept: two repository commands that
# need no build system, moved from the root Makefile to just.
#
# Rules: a recipe never calls make; inputs are repository files only; the
# commands are no longer Make targets. Applications are still built with
# make in their directory. Tested with just 1.59.0.

# Recipe lines run with /bin/sh, as GNU Make ran them.
set shell := ["/bin/sh", "-c"]

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
