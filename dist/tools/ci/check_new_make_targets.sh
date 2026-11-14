#!/bin/sh
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# This tool reports make targets that were declared since the base branch
# (first argument, default master; compared with the merge base) but are not
# in dist/tools/target_taxonomy/inventory.csv. It classifies them by the
# rules of the target taxonomy (groups 1/2A/2B/2C/3) and dry-runs them
# (make -n), so that the author can add them with their group.
"$(dirname "$0")"/../target_taxonomy/target_taxonomy.py check-new \
    --base "${1:-master}"
status=$?
if [ "$status" -eq 1 ]; then
    echo "New make targets: add them to dist/tools/target_taxonomy/inventory.csv"
elif [ "$status" -ne 0 ]; then
    echo "check_new_make_targets: the check itself failed (exit $status)"
fi

exit "$status"
