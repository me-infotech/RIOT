# Test log 2026-11-14 — build layer on nrf52840dk: Make vs. CMake + Ninja vs. Meson + Ninja (roadmap P6, D24)

Scenario S2 (`meson-vs-cmake.md` 3.4): Make stays the transitional resolver;
CMake and Meson read the same exported resolved state. Application
`examples/basic/hello-world`, board `nrf52840dk`, everything inside the
pinned riotbuild image (`riot/riotbuild@sha256:64b8e341…`: GNU Make 4.4.1,
CMake 4.2.3, Meson 1.12.1, Ninja 1.13.2, arm-none-eabi-gcc 10.3.1).
Tree: fresh clone of `RIOT_Test` `7de930980f` in `~/Documents/riot-p6-work`
(outside the repositories; the scratchpad was cleared twice by reboots).
Tools: `build-poc/` (`run_poc.sh`, `export_resolved_state.py`,
`gen_cmake.py`, `gen_meson.py`, `compare_flags.py`, `timing.sh`).
Evidence: `.claude/research/build-nrf52840dk/` (`SHA256SUMS`).

## 1. Resolved state

`make clean; make QUIET=0 -j1 all` → verbose log → `resolved-state.json`:
44 objects (all C), per object compiler, source, object path and exact
flags (65 flags; one file, `mpaland-printf/printf.c`, has
`-Wno-maybe-uninitialized` in addition); link flags; CPU `nrf52`;
modules and packages from `make info-modules` / `info-packages`; runtime
variables FLASHER, FFLAGS, TERMPROG, TERMFLAGS, PORT, SIZE, ELFFILE.
Finding: RIOT passes the `MODULE_*` defines through the generated
`riotbuild.h`, not as compiler flags; the defines are exactly modules +
packages (checked: `module_defines_consistent: true`).
Not exported: steps Make runs before compiling (package downloads into
`build/pkg`, generated headers `riotbuild.h`, `preprocessor_successor.h`);
CMake and Meson reuse their results from the same tree.

## 2. Parity with Make

| Check | CMake + Ninja | Meson + Ninja |
|---|---|---|
| build | ok (45 steps) | ok (45 steps) |
| `size` (text/data/bss) | 6892 / 0 / 2320 = Make | 6892 / 0 / 2320 = Make |
| `nm -n` sorted, with addresses (196 symbols) | **identical** | **identical** |
| per-file flags vs. resolved state | all 44 files: no flag missing, none added, same order | all present; **added** to every file: `-D_FILE_OFFSET_BITS=64`, `-fdiagnostics-color=always`, `-I.`, `-I../meson-src`, `-Ilibobjs<N>.a.p`; order of the resolved flags not kept |
| link order | Make's object order (source list in that order) | Make's object order (`extract_objects` one by one) |

The Meson additions do not change this firmware (identical symbols and
addresses), but they are flags RIOT did not ask for; Meson offers no
option to switch off `-D_FILE_OFFSET_BITS=64`.

## 3. Example targets (D24)

| Group | Target | Make | CMake | Meson |
|---|---|---|---|---|
| 2A | `info-modules` (61 modules) | `make info-modules` | custom target, output **identical** | run target, output **identical** |
| 2A | `info-cpu` | `nrf52` | **identical** | **identical** |
| 2B | `info-buildsize` | `size -d -B <elf>` | run: **identical** output | run: **identical** output |
| 2B | `flash-only` | `openocd.sh flash <elf>` | same command (compared with `ninja -t commands`, not run: no hardware) | same command (not run) |
| 2B | `term` | `pyterm -p /dev/ttyACM0 -b 115200 -ln … -rn <time>-hello-world-nrf52840dk` | same command, arguments unquoted (not run) | same command (not run) |
| 2C | `clean` | `make clean` | `ninja -t clean`: ELF removed | `ninja -t clean`: ELF removed |
| 3 | `all` | ELF | ELF, identical | ELF, identical |
| 3 | `flash` | `all` + flasher | custom target `DEPENDS` the ELF (command compared) | run target with the executable object (builds first; command compared) |

`distclean` (2C) has no build-tool counterpart: it also deletes package
downloads (`build/pkg`), which belong to the resolver/fetch step, not to
CMake/Meson. `test` (3) needs the board (not run).
Differences in the commands: Make wraps `info-buildsize` with
`|| echo ''`; Meson runs commands through its command runner with
`MESON_*` environment variables.

## 4. Size of the build description

| | CMake | Meson |
|---|---:|---:|
| generator (non-blank, non-comment lines) | 104 | 106 |
| generated description for hello-world (lines) | 109 (`CMakeLists.txt`) | 113 (`meson.build`) |
| workarounds needed | link rule replaced (`CMAKE_C_LINK_EXECUTABLE`) for Make's object/flag order; `CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY` | one static library per flag set (no per-file flags); objects extracted one by one for the link order; options `b_lundef`, `b_asneeded`, `b_staticpic`, `buildtype=plain`, `warning_level=0`; ELF passed as a path string so that 2B targets do not build |

## 5. Timing

`timing.sh`, 10 rounds inside the container on the host (Intel N150,
4 cores, `-j4`), wall time in ms, median and interquartile range
(`timing.txt`). "full" = after `clean` (packages already downloaded);
"incr" = after `touch main.c`.

| Measure | Make | CMake + Ninja | Meson + Ninja |
|---|---:|---:|---:|
| resolve / configure | 160 (149–180), make parse + resolution | **176** (174–186), `cmake` configure | 537 (516–557), `meson setup` |
| full build | 3972 (3733–4149) | **3073** (2995–3252) | 3209 (3135–3765) |
| no-op rebuild | 582 (556–589) | **8** (7–9) | **8** (8–9) |
| incremental (`main.c`) | 577 (562–600) | **273** (250–283) | 274 (262–294) |

Notes: CMake and Meson do not include the resolution (it ran once in Make
and was exported, S2); a complete S2 build is "resolve" + tool. Make's
no-op is dominated by re-parsing and the recursive module makes. The
roadmap's decision rule (`roadmap.md` P6.1: re-score if Meson configures
more than 2× faster) does not apply: **Meson's setup is about 3× slower
than CMake's configure** for the same description; the stress-test
assumption of `meson-vs-cmake.md` 3.5 ("Meson configures faster") is not
confirmed for this case.

## 6. Second application: gnrc_networking

Same pipeline (`run_poc.sh <work> examples/networking/gnrc/networking
nrf52840dk`; `run_poc.sh` now takes the application name from Make's
`APPLICATION`, which differs from the directory name here). Evidence:
`.claude/research/build-nrf52840dk/gnrc_networking/`.

| Check | CMake + Ninja | Meson + Ninja |
|---|---|---|
| objects | 153 (all C) | 153 |
| `size` text/data/bss | 95864 / 220 / 19956 = Make | = Make |
| `nm -n` with addresses (1074 symbols) | **identical** | **identical** |
| per-file flags | exact, same order (153/153) | all present; same additions as for hello-world |
| `info-modules` (208), `info-cpu` | identical | identical |
| `flash-only`, `term` commands | same as `make -n` | same |
| generated description (lines) | 327 | 331 |

`module_defines_consistent: true` (MODULE_* defines = modules + packages).

Timing (10 rounds, ms, median and IQR):

| Measure | Make | CMake + Ninja | Meson + Ninja |
|---|---:|---:|---:|
| resolve / configure | 177 (171–184) | **204** (190–230) | 650 (603–784) |
| full build | 14955 (14109–16012) | **14685** (14048–16149) | 15609 (14042–16941) |
| no-op rebuild | 1488 (1455–1574) | **12** (11–13) | **11** (9–12) |
| incremental (`main.c`) | 1585 (1517–1691) | 1241 (1191–1433) | **1207** (1178–1262) |

The full build is dominated by the compiler (IQRs overlap for all three);
the build tool matters for configure, no-op and incremental builds. Meson
again configures about 3× slower than CMake.

## Reading [inference]

- With the resolution kept outside the build tool (S2), both CMake and
  Meson reproduce Make's firmware bit for bit in symbols and sizes; the
  build tool does not need to know RIOT's module model.
- CMake reproduces the flags exactly; Meson adds its own flags and needs
  more workarounds for per-file flags and link order.
