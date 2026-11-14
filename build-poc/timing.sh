#!/bin/bash
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Build-layer timing (roadmap P6), run INSIDE the riotbuild container with the
# clone of run_poc.sh mounted at /riot. Prints "<tool> <measure> <ms>".
#   make:  resolve (parse + resolution, no build), full (after clean), noop,
#          incr (after touching main.c)
#   cmake/meson: config (fresh build dir), full, noop, incr
# Usage: timing.sh [runs] [app dir] [board]
N=${1:-10}; APP=/riot/${2:-examples/basic/hello-world}; BOARD=${3:-nrf52840dk}
P=/riot/poc
ms() { local s; s=$(date +%s%N); "$@" >/dev/null 2>&1 || echo "FAILED: $*" >&2
       echo $(( ($(date +%s%N) - s) / 1000000 )); }
for _ in $(seq "$N"); do
  make -C "$APP" BOARD="$BOARD" clean >/dev/null 2>&1
  echo "make resolve $(ms make -C "$APP" BOARD="$BOARD" info-debug-variable-BOARD)"
  echo "make full $(ms make -C "$APP" BOARD="$BOARD" -j4 all)"
  echo "make noop $(ms make -C "$APP" BOARD="$BOARD" -j4 all)"
  touch "$APP/main.c"
  echo "make incr $(ms make -C "$APP" BOARD="$BOARD" -j4 all)"

  rm -rf "$P/t-cmake"
  echo "cmake config $(ms cmake -G Ninja -S "$P/cmake-src" -B "$P/t-cmake" -DCMAKE_TOOLCHAIN_FILE="$P/cmake-src/toolchain.cmake")"
  echo "cmake full $(ms ninja -j4 -C "$P/t-cmake")"
  echo "cmake noop $(ms ninja -j4 -C "$P/t-cmake")"
  touch "$APP/main.c"
  echo "cmake incr $(ms ninja -j4 -C "$P/t-cmake")"

  rm -rf "$P/t-meson"
  echo "meson config $(ms meson setup --cross-file "$P/meson-src/cross.ini" -Dbuildtype=plain -Db_staticpic=false -Db_lundef=false -Db_asneeded=false -Dwarning_level=0 -Db_pch=false "$P/t-meson" "$P/meson-src")"
  echo "meson full $(ms ninja -j4 -C "$P/t-meson")"
  echo "meson noop $(ms ninja -j4 -C "$P/t-meson")"
  touch "$APP/main.c"
  echo "meson incr $(ms ninja -j4 -C "$P/t-meson")"
done
