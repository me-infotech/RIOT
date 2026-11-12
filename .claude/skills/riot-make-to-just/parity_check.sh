#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Parity check for migrated RIOT targets.
#
# Compares stdout, stderr and exit status of
#   (a) make <target> in the clean baseline checkout,
#   (b) make <target> in the candidate checkout (Make bridge),
#   (c) just <target> in the candidate checkout (direct recipe),
# and checks that `make -n <target>` in the candidate emits no compiler,
# linker or flasher command. Read-only: it never modifies either checkout
# beyond what the targets themselves do.
#
# Usage:
#   parity_check.sh [-b BASE] [-c CAND] [-a APPDIR] [-o OUTDIR] [-- VAR=VAL ...] TARGET...
#
# Example:
#   parity_check.sh -a examples/basic/hello-world -- BOARD=native64 \
#       info-modules info-cpu info-build
#
# Exit status: 0 if every target passes, 1 otherwise, 2 on usage errors.

set -u

BASE=/home/mohammadjavad/Documents/RIOT
CAND=/home/mohammadjavad/Documents/RIOT_Test
APPDIR=.
OUTDIR=$(mktemp -d "${TMPDIR:-/tmp}/riot-parity.XXXXXX")

while getopts "b:c:a:o:h" opt; do
    case $opt in
        b) BASE=$OPTARG ;;
        c) CAND=$OPTARG ;;
        a) APPDIR=$OPTARG ;;
        o) OUTDIR=$OPTARG; mkdir -p "$OUTDIR" ;;
        h) sed -n '5,22p' "$0"; exit 0 ;;
        *) exit 2 ;;
    esac
done
shift $((OPTIND - 1))

VARS=()
[ "${1:-}" = "--" ] && shift   # getopts usually consumes "--" already
while [ $# -gt 0 ] && [[ $1 == *=* ]]; do
    VARS+=("$1")
    shift
done
[ $# -gt 0 ] || { echo "usage: $0 [-b BASE] [-c CAND] [-a APPDIR] [-- VAR=VAL ...] TARGET..." >&2; exit 2; }

HAVE_JUST=1
command -v just >/dev/null 2>&1 || HAVE_JUST=0

echo "# Parity check $(date -Iseconds)"
echo "baseline : $BASE @ $(git -C "$BASE" rev-parse --short HEAD) ($(git -C "$BASE" status --short | wc -l) dirty)"
echo "candidate: $CAND @ $(git -C "$CAND" rev-parse --short HEAD) branch $(git -C "$CAND" branch --show-current) ($(git -C "$CAND" status --short | wc -l) dirty)"
echo "appdir   : $APPDIR   vars: ${VARS[*]:-<none>}"
echo "make     : $(make --version | head -1)"
if [ $HAVE_JUST = 1 ]; then echo "just     : $(just --version)"; else echo "just     : NOT INSTALLED (just column skipped)"; fi
echo "logs     : $OUTDIR"
echo
printf '| %-36s | %-6s | %-6s | %-6s | %-8s |\n' target make-br just no-build verdict
printf '|%s|%s|%s|%s|%s|\n' "--------------------------------------" "--------" "--------" "--------" "----------"

run() { # name dir cmd...
    local name=$1 dir=$2; shift 2
    (cd "$dir" && "$@") >"$OUTDIR/$name.out" 2>"$OUTDIR/$name.err"
    echo $? >"$OUTDIR/$name.rc"
    # Checkout roots differ by design; normalise them (longer path first,
    # since one may be a prefix of the other).
    local a=$CAND b=$BASE
    [ ${#BASE} -gt ${#CAND} ] && { a=$BASE; b=$CAND; }
    sed -i -e "s#$a#<RIOTBASE>#g" -e "s#$b#<RIOTBASE>#g" \
        "$OUTDIR/$name.out" "$OUTDIR/$name.err"
}

FAIL=0
for t in "$@"; do
    safe=${t//[^A-Za-z0-9_.-]/_}
    run "$safe.base" "$BASE/$APPDIR" make --no-print-directory "${VARS[@]}" "$t"
    run "$safe.make" "$CAND/$APPDIR" make --no-print-directory "${VARS[@]}" "$t"
    mk=PASS
    if ! cmp -s "$OUTDIR/$safe.base.out" "$OUTDIR/$safe.make.out" ||
       ! cmp -s "$OUTDIR/$safe.base.rc" "$OUTDIR/$safe.make.rc"; then
        mk=FAIL
    elif ! cmp -s "$OUTDIR/$safe.base.err" "$OUTDIR/$safe.make.err"; then
        mk=STDERR  # e.g. extra bridge frames on failure paths: document it
    fi

    js=SKIP
    if [ $HAVE_JUST = 1 ]; then
        run "$safe.just" "$CAND/$APPDIR" env "${VARS[@]}" just --working-directory "$CAND/$APPDIR" "$t"
        js=FAIL
        if cmp -s "$OUTDIR/$safe.base.out" "$OUTDIR/$safe.just.out" &&
           cmp -s "$OUTDIR/$safe.base.rc" "$OUTDIR/$safe.just.rc"; then
            js=PASS
            cmp -s "$OUTDIR/$safe.base.err" "$OUTDIR/$safe.just.err" || js=STDERR
        fi
    fi

    (cd "$CAND/$APPDIR" && make -n --no-print-directory "${VARS[@]}" "$t") \
        >"$OUTDIR/$safe.dry" 2>&1
    nb=PASS
    if grep -Eq '(^|[ /])(gcc|g\+\+|clang|cc|ld|ar|arm-none-eabi-[a-z+]+|riscv[0-9a-z_-]*-gcc|xtensa[a-z0-9_-]*-gcc|openocd|pyocd|edbg|bossac|esptool(\.py)?|avrdude|cmake|ninja|laze)( |$)' "$OUTDIR/$safe.dry"; then
        nb=FAIL
    fi

    verdict=PASS
    [ "$mk" = FAIL ] || [ "$js" = FAIL ] || [ "$nb" = FAIL ] && verdict=FAIL
    [ "$verdict" = PASS ] && { [ "$mk" = STDERR ] || [ "$js" = STDERR ]; } && verdict=DEVIATION
    [ "$verdict" = FAIL ] && FAIL=1
    printf '| %-36s | %-6s | %-6s | %-6s | %-8s |\n' "$t" "$mk" "$js" "$nb" "$verdict"
done

echo
echo "PASS = byte-identical stdout+stderr+exit; STDERR = stdout/exit identical, stderr differs (document as deviation);"
echo "no-build = 'make -n' in candidate shows no compiler/linker/flasher/cmake/ninja/laze call."
exit $FAIL
