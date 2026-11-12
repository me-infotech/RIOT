# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Repository information (imported by the root justfile; settings in
# just/settings.just). Recipes run in the RIOT root directory.

# Print the root-directory usage help.
[group('repository')]
welcome:
    @echo "Welcome to RIOT - The friendly OS for IoT!"
    @echo ""
    @echo "You executed 'just welcome' from the base directory."
    @echo "Applications are built with 'make' in the application's directory."
    @echo ""
    @echo "Please see our Quick Start Guide at:"
    @echo "    https://guide.riot-os.org/getting-started/installing/"
    @echo "You can ask questions or discuss with other users on our forum:"
    @echo "    https://forum.riot-os.org"
    @echo ""
    @echo "Repository commands (list them with 'just --list'), for example:"
    @echo " just generate-{board,driver,example,module,pkg,test,features}"
    @echo " just info-{applications,boards,emulated-boards} print-versions"
    @echo " just doc doc-{starlight,man,latex}"
    @echo "Still run with make in the base directory:"
    @echo " make info-applications-supported-boards"
    @echo " make clean distclean docclean pkg-clean doc-ci static-test"
    @echo ""
    @echo "==> tl;dr Try running:"
    @echo "    cd examples/basic/default"
    @echo "    make BOARD=<INSERT_BOARD_NAME>"

# Print the versions of the host toolchains.
[group('repository')]
print-versions:
    @./dist/tools/ci/print_toolchain_versions.sh

# BOARDS if set, otherwise every directory in BOARDSDIRS except `common`.
[doc('List all boards.')]
[group('repository')]
info-boards:
    #!/usr/bin/env bash
    set -e
    if [ "${BOARDS+x}" != x ]; then
        BOARDSDIRS="$_RIOT_BOARDSDIRS"
        # Every directory below each board directory, minus `common`, in byte
        # order without duplicates (Make: $(wildcard $(dir)/*/.), $(sort)).
        BOARDS=$(
            set -f
            for dir in $BOARDSDIRS; do
                set +f
                # Patterns in the directory part are expanded, too.
                for path in $dir/*/.; do
                    [ -d "$path" ] || continue
                    # Only the literal "$dir/" prefix is stripped; paths found
                    # through a pattern in $dir stay unchanged.
                    case $path in
                        "$dir"/*/.) name=${path#"$dir/"}; name=${name%/.} ;;
                        *) name=$path ;;
                    esac
                    if [ "$name" != common ]; then
                        printf '%s\n' "$name"
                    fi
                done
                set -f
            done | LC_ALL=C sort -u
        )
    fi
    # Printed like `echo $(BOARDS)` in /bin/sh, in the calling directory; the
    # value is passed as data, not re-parsed as shell code.
    cd "$_RIOT_JUST_CALLER"
    exec /bin/sh -c 'echo $1' sh "$BOARDS"

# EMULATED_BOARDS if given, otherwise the QEMU and mGBA boards and every board
# with a Renode script dist/board.resc.
[doc('List boards that run in an emulator.')]
[group('repository')]
info-emulated-boards:
    #!/usr/bin/env bash
    set -e
    if [ "$_RIOT_EMULATED_BOARDS" = "(derived)" ]; then
        BOARDSDIRS="$_RIOT_BOARDSDIRS"
        # The pattern text "$BOARDSDIRS/*/dist/board.resc" is split into
        # words; words without a match are dropped (Make: $(wildcard)).
        set -f
        words=($BOARDSDIRS/*/dist/board.resc)
        prefix="$(echo $BOARDSDIRS)/"
        set +f
        renode=()
        for word in "${words[@]}"; do
            for path in $word; do
                if [ -e "$path" ] || [ -L "$path" ]; then
                    renode+=("$path")
                fi
            done
        done
        # Remove "/dist/board.resc" and the board-directory prefix.
        boards="$_RIOT_EMULATED_BOARDS_FIXED"
        for path in "${renode[@]}"; do
            path=${path//\/dist\/board.resc/}
            path=${path//"$prefix"/}
            boards+=" $path"
        done
    else
        boards="$_RIOT_EMULATED_BOARDS"
    fi
    # Byte order without duplicates (Make: $(sort)).
    set -f
    boards=$(printf '%s\n' $boards | LC_ALL=C sort -u)
    set +f
    cd "$_RIOT_JUST_CALLER"
    exec /bin/sh -c 'echo $1' sh "$boards"

# APPLICATION_DIRS if given, otherwise every directory below APPS_BASE_DIRS
# with a Makefile, minus makefiles/app_dirs.blacklist (same derivation as
# APPLICATION_DIRS in makefiles/app_dirs.inc.mk).
[doc('List all application directories.')]
[group('repository')]
info-applications:
    #!/usr/bin/env bash
    dirs="$_RIOT_APPLICATION_DIRS"
    if [ "$dirs" = "(derived)" ]; then
        dirs=$(find $_RIOT_APPS_BASE_DIRS -name Makefile -type f | \
            xargs dirname | \
            grep -vF "/bin/" | \
            grep -vFf "$_RIOT_APPS_BLACKLIST" | \
            sort | uniq)
    fi
    exec /bin/sh -c 'for dir in $1; do echo $dir; done' sh "$dirs"

# Like Make's `$(Q)`, the command is printed when Q is set and empty.
[doc('List the serial devices of the host.')]
[group('repository')]
list-ttys:
    #!/usr/bin/env bash
    cmd="$_RIOT_RIOTTOOLS/usb-serial/ttys.py"
    if [ "${Q+x}" = x ] && [ -z "$Q" ]; then echo "$cmd"; fi
    exec $cmd
