set shell := ["bash", "-ec"]

# List all boards, excluding the common board directory.
info-boards:
    #!/usr/bin/env bash
    set -e
    if [ "${BOARDS+x}" = x ]; then
        printf '%s\n' "$BOARDS"
        exit 0
    fi
    riotbase="${RIOTBASE:-$PWD}"
    boarddirs="${BOARDSDIRS:-${EXTERNAL_BOARD_DIRS:-} ${RIOTBOARD:-$riotbase/boards}}"
    for dir in $boarddirs; do
        for board in "$dir"/*/; do
            [ -d "$board" ] || continue
            board=${board%/}
            board=${board##*/}
            [ "$board" = common ] || printf '%s\n' "$board"
        done
    done | sort -u | tr '\n' ' '
    echo

# List emulated boards.
info-emulated-boards:
    #!/usr/bin/env bash
    set -e
    if [ "${EMULATED_BOARDS+x}" = x ]; then
        printf '%s\n' "$EMULATED_BOARDS"
        exit 0
    fi
    riotbase="${RIOTBASE:-$PWD}"
    boarddirs="${BOARDSDIRS:-${EXTERNAL_BOARD_DIRS:-} ${RIOTBOARD:-$riotbase/boards}}"
    boards="microbit gba_cartridge"
    for dir in $boarddirs; do
        for resc in "$dir"/*/dist/board.resc; do
            [ -f "$resc" ] || continue
            board=${resc%/dist/board.resc}
            boards="$boards ${board##*/}"
        done
    done
    printf '%s\n' $boards | sort -u | tr '\n' ' '
    echo

# List application directories.
info-applications:
    #!/usr/bin/env bash
    set -e
    if [ "${APPLICATION_DIRS+x}" = x ]; then
        for dir in $APPLICATION_DIRS; do
            echo "$dir"
        done
        exit 0
    fi
    riotbase="${RIOTBASE:-$PWD}"
    find bootloaders examples fuzzing tests -name Makefile -type f \
        | xargs dirname \
        | grep -vF '/bin/' \
        | grep -vFf "$riotbase/makefiles/app_dirs.blacklist" \
        | sort -u

# Print Make's resolved build information.
info-build:
    @make --no-print-directory _info-build

# Print Make's resolved build information as JSON.
info-build-json:
    @make --no-print-directory _info-build-json

# List resolved modules.
info-modules:
    @make --no-print-directory _info-modules

# List resolved packages.
info-packages:
    @make --no-print-directory _info-packages

# Print the resolved CPU.
info-cpu:
    @make --no-print-directory _info-cpu

# List provided features.
info-features-provided:
    @make --no-print-directory _info-features-provided

# List required features.
info-features-required:
    @make --no-print-directory _info-features-required

# List missing features.
info-features-missing:
    @make --no-print-directory _info-features-missing

# List used features.
info-features-used:
    @make --no-print-directory _info-features-used

# List KConfig variables.
info-kconfig-variables:
    @make --no-print-directory _info-kconfig-variables

# List supported toolchains.
info-toolchains-supported:
    @make --no-print-directory _info-toolchains-supported

# Check whether the selected toolchain is supported.
check-toolchain-supported:
    @make --no-print-directory _check-toolchain-supported

# List supported programmers.
info-programmers-supported:
    @make --no-print-directory _info-programmers-supported

# Print the Rust toolchain integration details.
info-rust:
    @make --no-print-directory _info-rust

# List boards supported by the resolved application configuration.
info-boards-supported:
    @make --no-print-directory _info-boards-supported

# List boards missing required features.
info-boards-features-missing:
    @make --no-print-directory _info-boards-features-missing

# List boards using blacklisted features.
info-boards-features-blacklisted:
    @make --no-print-directory _info-boards-features-blacklisted

# List boards with conflicting features.
info-boards-features-conflicting:
    @make --no-print-directory _info-boards-features-conflicting

# List applications together with their supported boards.
info-applications-supported-boards:
    #!/usr/bin/env bash
    set -e
    if [ "${APPLICATION_DIRS+x}" = x ]; then
        make --no-print-directory "APPLICATION_DIRS=$APPLICATION_DIRS" \
            _info-applications-supported-boards
    else
        make --no-print-directory _info-applications-supported-boards
    fi

# Remove all build products through Make, retaining Make's computed directory state.
clean:
    @make --no-print-directory _clean

# Remove all package sources.
pkg-clean:
    @echo "Cleaning all package sources"
    rm -rf build/pkg

# Print toolchain versions.
print-versions:
    @./dist/tools/ci/print_toolchain_versions.sh

# Regenerate the feature makefile.
generate-features:
    @./dist/tools/features_yaml2mx/features_yaml2mx.py \
        features.yaml \
        --output-makefile makefiles/features_existing.inc.mk

# List serial tty devices.
list-ttys:
    @make --no-print-directory _list-ttys

# Reset the connected target using the configured programmer.
reset:
    @make --no-print-directory _reset

# List available Make targets.
help:
    @make --no-print-directory _help
