# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# RIOT task layer: repository commands that need no build system.
#
# Only group-1 targets live here: no application/board/CPU context, no build,
# no build artifact, no runtime, no artifact lifecycle. Rules:
#   - A recipe never calls make, neither directly nor through a script.
#   - Inputs are repository files, environment variables and command-line
#     settings (`just NAME=value <recipe>`); nothing comes from Make.
#   - These commands are no longer Make targets. Applications are still built
#     with make in their directory.
#
# Layout:
#   just/settings.just    all settings, defaults and inputs (single source)
#   just/repository.just  [repository] welcome, print-versions, info-*, list-ttys
#   just/generate.just    [generate]   generate-*, riotgen-installed
#   just/doc.just         [doc]        doc*, doxygen-*, starlight-*
#
# Recipes run in this directory (the RIOT root) unless they state otherwise.
# Tested with just 1.59.0.

# Recipe lines run with /bin/sh, as GNU Make ran them, so that quoting and
# `echo` behave as before.
set shell := ["/bin/sh", "-c"]

import 'just/settings.just'
import 'just/repository.just'
import 'just/generate.just'
import 'just/doc.just'

# List the recipes.
[private]
default:
    @{{ quote(just_executable()) }} --justfile {{ quote(justfile()) }} --list
