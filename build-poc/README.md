# build-poc — CMake + Ninja and Meson + Ninja from Make's resolved state (roadmap P6)

Proof of concept for the build layer (groups 2A/2B/2C/3), scenario S2 of
`riot-build-config-thesis/docs/05-migration-concept/meson-vs-cmake.md`:
Make stays the transitional resolver; CMake and Meson read the same
resolved state and must produce the same firmware. Board `nrf52840dk`
(D22), application `examples/basic/hello-world`, toolchain from the pinned
`riot/riotbuild` image. Not part of RIOT's build; nothing here is used by
`make`.

| File | Purpose |
|---|---|
| `export_resolved_state.py` | verbose Make log (+ optional runtime variables) → `resolved-state.json`: per object compiler, source, object path, exact flags; link flags; modules and CPU (from `-DMODULE_*`, `-DRIOT_CPU=`); FLASHER/FFLAGS/TERMPROG/TERMFLAGS/SIZE/ELFFILE |
| `gen_cmake.py` | `resolved-state.json` → `CMakeLists.txt` + toolchain file (per-source `COMPILE_OPTIONS`, Make's link order and link shape) |
| `gen_meson.py` | `resolved-state.json` → `meson.build` + cross file (one static library per flag set, objects extracted one by one in Make's link order) |

Example targets (D24) in both generated projects: `info-modules`,
`info-cpu` (2A, print the resolved state, no build), `info-buildsize`,
`flash-only`, `term` (2B, existing ELF / programmer / terminal, no build),
`flash` (3, build then flash); `clean` is the build tool's own (2C).

## Steps (inside the riotbuild container, repository mounted at /riot)

```sh
cd /riot/examples/basic/hello-world
make BOARD=nrf52840dk clean
make BOARD=nrf52840dk QUIET=0 -j1 all > make.log 2>&1    # resolver + baseline
for v in FLASHER FFLAGS TERMPROG TERMFLAGS PORT SIZE ELFFILE; do ...; done  # runtime.json
build-poc/export_resolved_state.py make.log hello-world nrf52840dk runtime.json > resolved-state.json
build-poc/gen_cmake.py resolved-state.json poc/cmake-src
build-poc/gen_meson.py resolved-state.json poc/meson-src
cmake -G Ninja -S poc/cmake-src -B poc/cmake-build -DCMAKE_TOOLCHAIN_FILE=poc/cmake-src/toolchain.cmake
ninja -C poc/cmake-build
meson setup --cross-file poc/meson-src/cross.ini -Dbuildtype=plain -Db_staticpic=false \
    -Db_lundef=false -Db_asneeded=false -Dwarning_level=0 -Db_pch=false poc/meson-build poc/meson-src
ninja -C poc/meson-build
```

Limits: the steps Make runs before compiling (package downloads into
`build/pkg`, generated headers such as `riotbuild.h`) are not exported; the
build tools reuse their results. Only C sources occur in this application.
Results and measurements: `.claude/research/test-logs/2026-11-14-build-layer-nrf52840dk.md`.
