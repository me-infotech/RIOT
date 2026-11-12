# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Generators (imported by the root justfile; settings in just/settings.just).
# Recipes run in the RIOT root directory.

# Regenerate makefiles/features_existing.inc.mk from features.yaml.
[group('generate')]
generate-features:
    @./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml --output-makefile makefiles/features_existing.inc.mk

# Check that `riotgen` is installed.
[group('generate')]
[no-exit-message]
riotgen-installed:
    #!/usr/bin/env bash
    {{ _colors }}
    command -v riotgen > /dev/null 2>&1 || \
    { $color_echo \
    "${color_red}'riotgen' command is not available.\nPlease consider installing it with 'pip install riotgen' or download it from https://pypi.python.org/pypi/riotgen.${color_reset}"; \
    exit 1; }

# Create a new board skeleton interactively with riotgen.
[group('generate')]
generate-board: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen board -i

# Create a new driver skeleton interactively with riotgen.
[group('generate')]
generate-driver: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen driver -i

# Create a new example application interactively with riotgen.
[group('generate')]
generate-example: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen example -i

# Create a new module skeleton interactively with riotgen.
[group('generate')]
generate-module: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen module -i

# Create a new package skeleton interactively with riotgen.
[group('generate')]
generate-pkg: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen pkg -i

# Create a new test application interactively with riotgen.
[group('generate')]
generate-test: riotgen-installed
    @RIOTBASE="$(pwd -P)" riotgen test -i
