# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Repository commands that need no build system (https://just.systems).
# just finds this file from any directory of the repository.

# Recipe lines run with /bin/sh, as GNU Make runs them.
set shell := ["/bin/sh", "-c"]

# List the recipes.
[private]
default:
    @{{ quote(just_executable()) }} --justfile {{ quote(justfile()) }} --list

# Formerly `make list-ttys`; runs in the calling directory, without
# arguments, as Make did.
# List the serial TTYs connected to this host.
[no-cd]
list-ttys:
    @{{ justfile_directory() }}/dist/tools/usb-serial/ttys.py
