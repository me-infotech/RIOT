#!/bin/sh
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# This tool checks that every Makefile.dep generated from a deps.yaml
# (dist/tools/riot_deps) is up to date. It writes nothing.
"$(dirname "$0")"/../riot_deps/riot_deps.py generate --check --all || {
    echo "Forgot to run just generate-deps after updating a deps.yaml!"
    exit 1
}

exit 0
