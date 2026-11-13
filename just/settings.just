# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Central settings of the RIOT task layer (imported by the root justfile).
# Every constant, default and input of the recipes is declared here; the
# recipe files in this directory contain only the steps.

# ---------------------------------------------------------------- constants
#
# Single source for values that Make still needs: doc/doxygen/Makefile
# (`doc-ci`) and makefiles/app_dirs.inc.mk (`clean`, `distclean`) read them
# with `just --evaluate <NAME>`.

# Minimum Doxygen version; `doc-ci` downloads exactly this release. When
# changing it, also update DOXYGEN_TGZ_SHA512 in doc/doxygen/Makefile.
DOXYGEN_MIN_VERSION := "1.15.0"

# Directories that contain RIOT applications. The list of application
# directories is derived from them twice: by `info-applications`
# (just/repository.just) and by makefiles/app_dirs.inc.mk for the Make targets
# `clean`, `distclean` and `info-applications-supported-boards`; keep the two
# derivations alike.
APPS_BASE_DIRS := "bootloaders examples fuzzing tests"

# Boards that run in QEMU and mGBA; Renode boards are found through their
# dist/board.resc script.
EMULATED_BOARDS_QEMU := "microbit"
EMULATED_BOARDS_MGBA := "gba_cartridge"

# ---------------------------------------------------------------- inputs
#
# Inputs given on the command line, like Make command-line variables:
#
#     just APPLICATION_DIRS="examples/basic/hello-world" info-applications
#     just DOCUMENTATION_FORMAT="html man" doc
#
# The environment does not set them (Make assigned them with `:=`).
# "(derived)" means not given: the recipe derives the value.
#
# APPLICATION_DIRS      application directories for info-applications
# EMULATED_BOARDS       board list for info-emulated-boards
# DOCUMENTATION_FORMAT  Doxygen outputs of doc, doc-man, doc-latex
#                       (html, man, latex, check; empty: none)
# Q                     command echo prefix for list-ttys; empty: print
#                       the command (Make's command-line `Q=`)
APPLICATION_DIRS := "(derived)"
EMULATED_BOARDS := "(derived)"
DOCUMENTATION_FORMAT := "(derived)"
Q := "(derived)"

# Inputs taken from the environment (Make: `?=`; a set but empty value counts
# as set, as in Make). Their defaults are derived here, once:
#
# BOARDS                board list for info-boards (default: all boards)
# EXTERNAL_BOARD_DIRS   additional board directories (default: none)
# RIOTBOARD             RIOT's board directory
# BOARDSDIRS            board directories
# RIOTTOOLS             host tools directory
# DOXYGEN               Doxygen program
# RIOTBASE              RIOT checkout; its default differs per command, as it
#                       did in the Makefiles that defined these commands:
#                       boards: this directory (also when empty),
#                       info-applications: ".", documentation: git top level
#                       (resolved by the doc recipes only: a backtick here
#                       would run git, and print its errors, for every recipe)
# QUIET                 not 1: list-ttys prints its command (default: 1;
#                       also `just QUIET=0`, as on the Make command line)
# CC_NOCOLOR            1: no coloured messages
RIOTBOARD := env("RIOTBOARD", (if env("RIOTBASE", "") == "" { justfile_directory() } else { env("RIOTBASE") }) + "/boards")
BOARDSDIRS := env("BOARDSDIRS", env("EXTERNAL_BOARD_DIRS", "") + " " + RIOTBOARD)
RIOTTOOLS := env("RIOTTOOLS", justfile_directory() + "/dist/tools")
DOXYGEN := env("DOXYGEN", "doxygen")
APPS_BLACKLIST := env("RIOTBASE", ".") + "/makefiles/app_dirs.blacklist"
DOC_RIOTBASE := env("RIOTBASE", "(git top level)")
QUIET := env("QUIET", "1")

# Settings passed to the recipe scripts through the environment, never pasted
# into script text, so that unusual characters cannot change a script.
export _RIOT_JUST_ROOT := justfile_directory()
export _RIOT_JUST_CALLER := invocation_directory()
export _RIOT_BOARDSDIRS := BOARDSDIRS
export _RIOT_RIOTTOOLS := RIOTTOOLS
export _RIOT_DOXYGEN := DOXYGEN
export _RIOT_APPS_BLACKLIST := APPS_BLACKLIST
export _RIOT_DOC_RIOTBASE := DOC_RIOTBASE
export _RIOT_DOXYGEN_MIN_VERSION := DOXYGEN_MIN_VERSION
export _RIOT_APPS_BASE_DIRS := APPS_BASE_DIRS
export _RIOT_EMULATED_BOARDS_FIXED := EMULATED_BOARDS_QEMU + " " + EMULATED_BOARDS_MGBA
export _RIOT_APPLICATION_DIRS := APPLICATION_DIRS
export _RIOT_EMULATED_BOARDS := EMULATED_BOARDS
export _RIOT_DOCUMENTATION_FORMAT := DOCUMENTATION_FORMAT
export _RIOT_QUIET := QUIET
export _RIOT_Q := Q

# ---------------------------------------------------------------- output

# Colour set-up for the shebang recipes (mirrors makefiles/color.inc.mk):
# colours only when stdout and stderr are terminals and CC_NOCOLOR is not 1.
# Without colours, `/usr/bin/env echo` prints `\n` literally, as in Make.
_colors := '''
color_red=; color_reset=; color_echo="/usr/bin/env echo"
if [ "${CC_NOCOLOR-}" != 1 ] && [ -t 1 ] && [ -t 2 ]; then
    color_red='\033[1;31m'; color_reset='\033[0m'
    if [ "$(uname -s)" = Darwin ]; then color_echo="echo -e"; else color_echo="/usr/bin/env echo -e"; fi
fi
'''
