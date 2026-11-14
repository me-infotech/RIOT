#!/bin/bash
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Roadmap P6 proof of concept, end to end (see README.md):
#   1. fresh clone of this repository into <workdir>/riot
#   2. Make baseline + verbose log + runtime variables (riotbuild image)
#   3. export resolved-state.json, generate CMake and Meson projects
#   4. build with CMake + Ninja and Meson + Ninja
#   5. parity: size, nm (with addresses), per-file flags, example targets
# Usage: run_poc.sh <workdir> [app] [board]
set -u
W=$(realpath -m "$1"); APP_DIR=${2:-examples/basic/hello-world}; BOARD=${3:-nrf52840dk}
APP=$(basename "$APP_DIR")
HERE=$(cd "$(dirname "$0")" && pwd)
IMG=docker.io/riot/riotbuild@sha256:64b8e341a0ad96309c46169f6425e84e00bfc21291044db1c88c723e523a0a90
mkdir -p "$W/out"
[ -d "$W/riot" ] || git clone -q "$HERE/.." "$W/riot"
R="$W/riot"; O="$W/out"
run() { # run a command in the container, /riot = clone
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
    -v "$R:/riot" -w /riot "$IMG" "$@"
}
echo "== clone $(git -C "$R" log --oneline -1)"
echo "== 2. Make baseline"
run make -C "/riot/$APP_DIR" BOARD="$BOARD" clean >/dev/null 2>&1
run make -C "/riot/$APP_DIR" BOARD="$BOARD" QUIET=0 -j1 all > "$O/make.log" 2>&1 || { echo "make failed"; exit 1; }
{
  echo "{"
  first=1
  for v in FLASHER FFLAGS TERMPROG TERMFLAGS PORT SIZE ELFFILE; do
    val=$(run make --no-print-directory -C "/riot/$APP_DIR" BOARD="$BOARD" "info-debug-variable-$v" 2>/dev/null | tail -1)
    [ $first = 1 ] || echo ","
    first=0
    printf '  "%s": %s' "$v" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$val")"
  done
  for v in modules packages; do
    run make --no-print-directory -C "/riot/$APP_DIR" BOARD="$BOARD" "info-$v" > "$O/resolver.$v.txt" 2>/dev/null
    printf ',\n  "%s": %s' "$(echo $v | tr a-z A-Z)" "$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read().split()))' "$O/resolver.$v.txt")"
  done
  echo; echo "}"
} > "$O/runtime.json"
echo "== 3. export + generate"
python3 "$HERE/export_resolved_state.py" "$O/make.log" "$APP" "$BOARD" "$O/runtime.json" > "$O/resolved-state.json" || exit 1
python3 "$HERE/gen_cmake.py" "$O/resolved-state.json" "$R/poc/cmake-src" || exit 1
python3 "$HERE/gen_meson.py" "$O/resolved-state.json" "$R/poc/meson-src" || exit 1
echo "== 4. build"
run cmake -G Ninja -S /riot/poc/cmake-src -B /riot/poc/cmake-build \
  -DCMAKE_TOOLCHAIN_FILE=/riot/poc/cmake-src/toolchain.cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON > "$O/cmake-config.log" 2>&1 || { echo "cmake config failed"; exit 1; }
run ninja -C /riot/poc/cmake-build > "$O/cmake-build.log" 2>&1 || { echo "cmake build failed"; exit 1; }
WIPE=; [ -d "$R/poc/meson-build" ] && WIPE=--wipe
run meson setup $WIPE --cross-file /riot/poc/meson-src/cross.ini -Dbuildtype=plain -Db_staticpic=false \
  -Db_lundef=false -Db_asneeded=false -Dwarning_level=0 -Db_pch=false \
  /riot/poc/meson-build /riot/poc/meson-src > "$O/meson-config.log" 2>&1 || { echo "meson setup failed"; exit 1; }
run ninja -C /riot/poc/meson-build > "$O/meson-build.log" 2>&1 || { echo "meson build failed"; exit 1; }
echo "== 5. parity"
MAKE_ELF="/riot/$APP_DIR/bin/$BOARD/$APP.elf"
for t in make cmake meson; do
  case $t in make) e=$MAKE_ELF ;; *) e=/riot/poc/$t-build/$APP.elf ;; esac
  run sh -c "arm-none-eabi-size $e | tail -1 | awk '{print \$1, \$2, \$3}'; arm-none-eabi-nm -n $e | sort" > "$O/elf.$t.txt"
done
for t in cmake meson; do
  cmp -s "$O/elf.make.txt" "$O/elf.$t.txt" && echo "$t: size + nm identical to make ($(wc -l < "$O/elf.make.txt") lines)" \
    || echo "$t: DIFFERS from make"
done
python3 "$HERE/compare_flags.py" "$O/resolved-state.json" "$R/poc/cmake-build/compile_commands.json" cmake
python3 "$HERE/compare_flags.py" "$O/resolved-state.json" "$R/poc/meson-build/compile_commands.json" meson
echo "== example targets"
run make --no-print-directory -C "/riot/$APP_DIR" BOARD="$BOARD" info-modules > "$O/t.make.info-modules" 2>&1
run make --no-print-directory -C "/riot/$APP_DIR" BOARD="$BOARD" info-cpu > "$O/t.make.info-cpu" 2>&1
for t in cmake meson; do
  for tg in info-modules info-cpu; do
    # ninja prints "ninja: Entering directory"; keep only the target output
    run ninja --quiet -C /riot/poc/$t-build $tg 2>&1 | grep -v '^ninja: Entering directory' > "$O/t.$t.$tg"
    cmp -s "$O/t.make.$tg" "$O/t.$t.$tg" && echo "$t $tg: identical to make" || echo "$t $tg: DIFFERS"
  done
done
echo "== done"
echo "== group 2B/3 targets: commands (no hardware: compared, not run)"
norm() { sed -E -e 's/[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}\.[0-9]{2}\.[0-9]{2}/<TIME>/g' \
  -e "s#/riot/$APP_DIR/bin/$BOARD/$APP.elf#<ELF>#g" -e "s#/riot/poc/(cmake|meson)-build/$APP.elf#<ELF>#g" \
  -e "s#${APP}\.elf#<ELF>#g" -e 's/[[:space:]]+/ /g; s/ $//'; }
for tg in info-buildsize flash-only term; do
  run make --no-print-directory -C "/riot/$APP_DIR" BOARD="$BOARD" -n "$tg" 2>/dev/null | tail -1 | norm > "$O/c.make.$tg"
  for t in cmake meson; do
    run ninja -C /riot/poc/$t-build -t commands "$tg" 2>/dev/null | tail -1 | norm > "$O/c.$t.$tg"
  done
done
echo "-- see $O/c.*: make -n vs. ninja -t commands"
for t in cmake meson; do
  run sh -c "ninja -C /riot/poc/$t-build -t clean >/dev/null; test -e /riot/poc/$t-build/$APP.elf && echo '$t clean: ELF still there' || echo '$t clean: ELF removed'"
done
echo "== done 2"
