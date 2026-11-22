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

# Rules: a recipe never calls make; inputs are repository files only; the
# commands are no longer Make targets. The applications of step G3-1 are
# built with `just build` (CMake + Ninja, dist/tools/cmake_gen), flashed
# with `just flash` (dist/tools/flash), distributed as binaries with
# `just bindist` (dist/tools/bindist) and cleaned with `just clean` and
# `just distclean` (dist/tools/clean); their terminal is opened with `just
# term` and `just cleanterm` (dist/tools/term) and their debugger with `just
# debug`, `just debug-server` and `just debug-client` (dist/tools/debug);
# their test scripts run with `just test` and `just test-available`
# (dist/tools/test); all others are still built, flashed, distributed,
# cleaned, opened, debugged and tested with make in their directory.
# Tested with just 1.59.0.

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

# Moved from the root Makefile (step G2C-3). Repository-global, like Make:
# always <repository>/build/pkg, whatever the calling directory, BUILD_DIR or
# PKGDIRBASE; no arguments.
# Remove the package sources of all applications (build/pkg).
pkg-clean: (_pkg-clean justfile_directory() "echo")

# The steps of `pkg-clean`, in <dir>. The root `make distclean` runs them with
# Make's CURDIR (as `make -f <repository>/Makefile distclean` did) and a mode
# for Make's options: echo (default), silent (`make -s`: the command line is
# not shown, as Make hid it) or dry-run (`make -n`: print the commands Make
# printed, change nothing). Only <dir>/build/pkg is ever removed.
[private]
_pkg-clean dir mode:
    #!/bin/sh
    set -e
    dir={{ quote(dir) }} mode={{ quote(mode) }}
    case "$dir" in
        /*) ;;
        *) echo "pkg-clean: not an absolute directory: $dir" >&2; exit 1 ;;
    esac
    case "$mode" in
        echo|silent|dry-run) ;;
        *) echo "pkg-clean: unknown mode: $mode" >&2; exit 1 ;;
    esac
    cd "$dir"
    msg="Cleaning all package sources" pkg=build/pkg
    if [ "$mode" = dry-run ]; then
        echo "echo \"$msg\""
        echo "rm -rf $pkg"
        exit 0
    fi
    echo "$msg"
    [ "$mode" = silent ] || echo "rm -rf $pkg"
    rm -rf "$pkg"

# Moved from Makefile.include (application level). Runs in the calling
# directory, without arguments and with the absolute path, as Make did.
# List the serial TTYs connected to this host.
[no-cd]
list-ttys:
    @{{ justfile_directory() }}/dist/tools/usb-serial/ttys.py

# Regenerate the Make files (Makefile.dep, Makefile.features) from their YAML source.
generate-config-data:
    @./dist/tools/config_data/config_data.py generate

# Build an application without Make: CMake + Ninja from the data (step G3-1).
# Example: just build examples/basic/hello-world nrf52840dk; VAR=VALUE as for make.
build app board *vars:
    @./dist/tools/cmake_gen/cmake_gen.py build -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Regenerate the Make adapters (flash.inc.mk, <x>.flash.inc.mk) from the flash data
# (maintenance of step G3-2; private: not a former Make target).
[private]
generate-flash-data:
    @./dist/tools/flash/flash.py generate

# Build (as `just build`) and flash an application without Make (step G3-2).
# Example: just flash examples/basic/hello-world nrf52840dk PROGRAMMER=openocd
flash app board *vars:
    @./dist/tools/flash/flash.py flash -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Regenerate the Make adapters (<x>.dist.inc.mk) from the distribution data
# (maintenance of step G3-3; private: not a former Make target).
[private]
generate-dist-data:
    @./dist/tools/bindist/bindist.py generate

# Build (as `just build`, in Make's BINDIR <app>/bin/<board>) and make the
# binary distribution <app>/bindist without Make (step G3-3).
# Example: just bindist examples/advanced/bindist nrf52840dk
bindist app board *vars:
    @./dist/tools/bindist/bindist.py bindist -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Regenerate the Make adapters (<x>.clean.inc.mk) from the clean data
# (maintenance of step G2C-1; private: not a former Make target).
[private]
generate-clean-data:
    @./dist/tools/clean/clean.py generate

# Remove what `make clean` removes (package build directories, Make's BINDIR
# <app>/bin/<board>, the scan-build reports) and the build directory of
# `just build`/`just flash` (<app>/bin/cmake-<board>) without Make (step G2C-1).
# Example: just clean examples/basic/hello-world nrf52840dk
clean app board *vars:
    @./dist/tools/clean/clean.py clean -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Remove what `make distclean` of the application removes (per package of
# PKG_PATHS its build directory and its source directory in BUILD_DIR/pkg,
# then BINDIRBASE <app>/bin) and the build directory of `just build`/`just
# flash` when it is not below BINDIRBASE, without Make (step G2C-2).
# Example: just distclean examples/basic/hello-world nrf52840dk
distclean app board *vars:
    @./dist/tools/clean/clean.py distclean -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Regenerate the Make adapters (term.inc.mk, <x>.term.inc.mk, debug.inc.mk,
# <x>.debug.inc.mk) from the terminal and debugger data (maintenance of step
# G2B-1; private: not a former Make target).
[private]
generate-term-data:
    @./dist/tools/term/term.py generate

# Open the terminal of an application on the board without Make, as `make
# term` (step G2B-1): RIOT_TERMINAL (default pyterm), PORT, BAUD, … as for
# make; nothing is built (flash first with `just flash`).
# Example: just term examples/basic/hello-world nrf52840dk RIOT_TERMINAL=picocom
term app board *vars:
    @./dist/tools/term/term.py term -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# The terminal without pyterm's logging and prefixes, as `make cleanterm`
# (step G2B-1). Example: just cleanterm examples/basic/hello-world nrf52840dk
cleanterm app board *vars:
    @./dist/tools/term/term.py cleanterm -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Start the debugger (GDB with the programmer's GDB server) of an application
# on the board without Make, as `make debug` (step G2B-2): PROGRAMMER,
# DEBUG_ADAPTER_ID, MOST_RECENT_PORT, … as for make; the image must exist
# (Make's BINDIR <app>/bin/<board>, or BINDIR=…): `just flash … && just debug …`.
# Example: just debug examples/basic/hello-world nrf52840dk PROGRAMMER=openocd
debug app board *vars:
    @./dist/tools/debug/debug.py debug -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Only the GDB server of the programmer, as `make debug-server` (step G2B-2).
# Example: just debug-server examples/basic/hello-world nrf52840dk
debug-server app board *vars:
    @./dist/tools/debug/debug.py debug-server -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Only GDB, connected to a running debug server, as `make debug-client`
# (step G2B-2). Example: just debug-client examples/basic/hello-world nrf52840dk
debug-client app board *vars:
    @./dist/tools/debug/debug.py debug-client -C {{ quote(app) }} BOARD={{ quote(board) }} {{ vars }}

# Run the test scripts of an application on the board without Make, as `make
# test` (step G2B-3): TESTS (default: the executable files of <app>/tests),
# TEST_EXECUTOR, TEST_EXECUTOR_FLAGS as for make; nothing is built or flashed
# (flash first with `just flash`). Each argument is one VAR=VALUE, so TESTS
# can name several scripts. The terminal inside a test is still opened by
# make (dist/pythonlibs/testrunner/spawn.py).
# Example: just test examples/basic/hello-world nrf52840dk TESTS="tests/01-run.py"
[positional-arguments]
test app board *vars:
    @app="$1" board="$2"; shift 2; exec ./dist/tools/test/test.py test -C "$app" BOARD="$board" "$@"

# Exit 0 if the application has tests for the board, as `make test/available`
# (step G2B-3). Example: just test-available examples/basic/hello-world nrf52840dk
[positional-arguments]
test-available app board *vars:
    @app="$1" board="$2"; shift 2; exec ./dist/tools/test/test.py test/available -C "$app" BOARD="$board" "$@"
