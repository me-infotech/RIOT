set shell := ["bash", "-ec"]

# List all boards, excluding the common board directory.
info-boards:
    #!/usr/bin/env bash
    set -e
    if [ "${BOARDS+x}" = x ]; then
        echo $BOARDS
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
        echo $EMULATED_BOARDS
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

# Remove all build products through Make, retaining Make's computed directory state.
clean:
    make --no-print-directory _clean

# Remove all package sources.
pkg-clean:
    echo "Cleaning all package sources"
    rm -rf build/pkg

# Print toolchain versions.
print-versions:
    ./dist/tools/ci/print_toolchain_versions.sh

# Regenerate the feature makefile.
generate-features:
    ./dist/tools/features_yaml2mx/features_yaml2mx.py \
        features.yaml \
        --output-makefile makefiles/features_existing.inc.mk

# List serial tty devices.
list-ttys:
    make --no-print-directory _list-ttys

# Reset the connected target using the configured programmer.
reset:
    make --no-print-directory _reset

# List available Make targets.
help:
    make --no-print-directory _help
