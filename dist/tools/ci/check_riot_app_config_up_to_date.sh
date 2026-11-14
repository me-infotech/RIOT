#!/bin/sh
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# This tool checks that every riot-app.inc.mk is up to date with the
# riot-app.yaml next to it. Unlike the features check it writes nothing.
"$(dirname "$0")"/../riot_app_config/riot_app_config.py --check --all || {
    echo "Forgot to run just generate-app-config after updating a riot-app.yaml!"
    exit 1
}

exit 0
