# Test log 2026-11-14 — hello-world on nrf52840dk built without Make (P6 part A, D26)

Decisions (user, D26): flags from the translated `Makefile.include` files,
`$(shell …)` as named Python blocks; sources from the translated module
Makefiles; prerequisites by calling RIOT's own scripts/commands; scope
hello-world on `nrf52840dk`. Code (commit `ab4ad980fc`, review fixes in the working tree, §7):
`build-poc/resolver/` (`translate_deps.py`, `makeexpr.py`, `resolver.py`,
`flags.py`, `submake.py`, `prestep.py`, `build_state.py`) and
`build-poc/gen_cmake.py`, `gen_meson.py`. Evidence:
`.claude/research/build-without-make/` (`SHA256SUMS`).

## 1. Translation of the build make files

`translate_deps.py <riot> rules.json --build` (all `Makefile.include`,
`makefiles/**/*.mk`, `Makefile.base`, `Makefile.modules`, the dependency
files and everything they include): 2126 files, 2122 fully translated;
18829 statements: 17828 structured, 994 expression fallback, 7
unsupported (not reached for hello-world). New constructs handled: rules
and recipes (kept as text, no effect on variables), `define … endef`,
`export`/`unexport`/`override`/`undefine`, top-level function calls,
`$(eval …)`, computed variable names, single-letter variables (`$_`),
recipe continuation lines (backslash-newline kept for the shell). The
evaluator gained `wildcard`, `addprefix`, `addsuffix`, `abspath`,
`realpath`, `dir`, `notdir`, `basename`, `suffix`, `join`, `origin`,
`flavor`, `value`, `info`/`warning`/`error`, `shell` (named blocks),
`eval`, `file`, `foreach` (results not stripped, `$(NEWLINE)` survives).

## 2. Variables of Makefile.include (flags.py)

`Makefile.include` evaluated as data, incl. the self-including
`dependency_resolution.inc.mk` and `features_check.inc.mk` (no Python
replacement needed any more). Compared with `make
info-debug-variable-<VAR>` (host, same tree; Make prints through `echo`,
so the Python value was passed through the same `echo`):

| Variable | Result |
|---|---|
| CFLAGS (44 words), INCLUDES (16), LINKFLAGS (49), CFLAGS_WITH_MACROS (110, input of riotbuild.h), BASELIBS (24), USEMODULE (61) | **identical** (same order) |

`$(shell …)`: 21 distinct calls for hello-world/nrf52840dk, covered by 13
named blocks (5 of them run the matched host command verbatim, see below) (`flags.py` `SHELL_BLOCKS`): pure Python for `getconf
LONG_BIT`, `uname -m -s`, `$((…))` arithmetic, `command -v`, `date`; git
(`rev-parse --show-toplevel`, `describe`, `rev-parse --abbrev-ref`) run
directly; toolchain probes (compiler/linker flag tests, include
directories, gdb, `-dumpversion`) run the probe command of the host tool.
An unknown `$(shell)` stops the run.

## 3. Objects and compile flags (submake.py)

The recursion over DIRS (application → `cpu/nrf52`, `boards/nrf52840dk`,
`boards`, `cpu`, `core`, `core/lib`, `drivers`, `sys`, and the
subdirectories their Makefiles add) and the package `all` recipes
(`$(MAKE) -C $(PKG_SOURCE_DIR) -f …`) are evaluated from the translated
rules, each with the exported variables of its parent. Compared with the
objects of Make's verbose build (container):

| | Make | Python |
|---|---:|---:|
| objects | 44 | 44, same paths |
| same source | | 44/44 |
| same compile flags, same order | | 44/44 |

Found on the way: `pkg/pkg.mk` adds `CFLAGS += -Wno-maybe-uninitialized`
in the package make, and the package's sub-make inherits it through the
exported CFLAGS; `cpu/nrf52/vectors` uses `SRC_NOLTO`; generated `.d`
files are included by `Makefile.base`.

## 4. Prerequisites without Make (prestep.py)

RIOT has no stand-alone scripts for package preparation; the steps are
recipes in `pkg/pkg.mk`, `cpu/nrf5x_common/Makefile.nrfx` and
`Makefile.include`. `prestep.py` is a minimal recipe runner: for every
target in `BUILDDEPS` (`fetch_nrfx_vendor_headers`,
`preprocessor_successor.h`, `riotbuild.h`, `pkg-prepare`) it runs the
recipes of the target and its prerequisites in dependency order; every
command runs unchanged with `/bin/sh` (git clone/sparse checkout/fetch/
checkout, `git am` of the patches, `cp` of the vendor headers,
`generate_pp_successor_header.sh`, `genconfigheader.sh | lazysponge`,
`sed`); a recursive `$(MAKE)` in a recipe is evaluated from the translated
rules instead of starting Make (3 such calls). Not modelled: time stamps
beyond "file exists and no prerequisite was remade", parallelism,
`.SECONDEXPANSION`.

Fresh clone of `RIOT_Test` (`git log -1` in `clone-commit.txt`) without
`build/` and `bin/`; `prestep.py` in the riotbuild container: exit 0, 80
log lines. Compared with the results of Make's build in the earlier clone:

| Output | Result |
|---|---|
| `build/pkg/cmsis`, `build/pkg/mpaland-printf` (patched), `build/nrf5x_nrfx_mdk/nrf52` (sparse, patched, vendor headers) | **identical** file trees (SHA-256 over all files except `.git`, `.pkg-state*`) |
| `preprocessor_successor.h` | identical |
| `riotbuild.h` | identical except `RIOT_VERSION`/`RIOT_VERSION_CODE` (the clones are on different commits; `git describe`) |

## 5. Build-state export without Make and the build

`build_state.py` writes `resolved-state.json` (same schema as
`export_resolved_state.py`) from Python only. Against Make's export: 61
modules, 44 objects with identical flags, same linker, identical link
flags and output; runtime variables identical except `TERMFLAGS`
(contains a time stamp from `$(shell date …)`).

In the fresh clone (Make never ran before): `gen_cmake.py` /
`gen_meson.py` on the Python state, build with CMake + Ninja and Meson +
Ninja in the container; **then** `make all` in the same clone as the
reference:

| | size text/data/bss | `nm` (196 lines) | firmware image (`objcopy -O binary`) SHA-256 |
|---|---|---|---|
| Make | 6892 / 0 / 2320 | – | `26c63130…a0e4` |
| CMake + Ninja (no Make) | 6892 / 0 / 2320 | identical | **identical** |
| Meson + Ninja (no Make) | 6892 / 0 / 2320 | identical | **identical** |

Every docker run was a one-shot container (`--rm`); none was left running.

## 6. Second application: gnrc_networking (user decision 2026-11-14)

Same fresh clone (Make had never run for this application), same tools
(commit `ab4ad980fc`), unchanged code: `prestep.py` exit 0,
`build_state.py` exit 0 (208 modules, 153 objects), CMake + Ninja and
Meson + Ninja built from the Python state, then `make all` in the same
clone as the reference (evidence: `gnrc_networking/`):

| | size text/data/bss | `nm` (1074 lines) | firmware image SHA-256 |
|---|---|---|---|
| Make | 95860 / 220 / 19956 | – | see `firmware-sha256.txt` |
| CMake + Ninja (no Make) | 95860 / 220 / 19956 | identical | **identical** |
| Meson + Ninja (no Make) | 95860 / 220 / 19956 | identical | **identical** |

(text 95860 here vs. 95864 in `2026-11-14-build-layer-nrf52840dk.md` §6:
other commit, the version string in the firmware differs in length.)

## 7. Independent review and fixes (2026-11-14)

A read-only review (subagent) of `ab4ad980fc` found 8 major and about 15
minor/nit findings; it confirmed the measured results for the two
applications but showed that the evaluator did not reproduce GNU Make in
general. Fixed (working tree):

| Finding | Fix | Verified |
|---|---|---|
| `$(1)`/`${1}` inside `$(call)` read a global variable "1" | parameters from the call | `version_is_greater_or_equal` = RIOT's `test-strings.mk` expectations in 10/10 cases (`make … test-version_is_greater_or_equal` passes in RIOT) |
| command-line variables assigned with `:=`, overridable, not passed on | protected command-line layer, `override` honoured, passed to every sub-make (MAKEFLAGS) | test Makefile vs. GNU Make 4.3: same values |
| target-/pattern-specific variables dropped (LTOFLAGS hard-coded) | recorded and applied when a target is made / an object is compiled; on the link step they stop the run | same test Makefile: same value |
| nested sub-makes got only the top-level environment | children inherit the exported variables of their parent sub-make | — (code) |
| packages built only from text directly under `all:` | default goal of the package make built with the recipe runner; recursive makes are module builds; other commands in the goal recipe stop the run | both applications: same objects |
| recipe runner without time stamps, order-only treated as normal, Python's environment, no guards | time-stamp comparison, order-only separate, Make's exported environment, `rm -r/-f` only inside `BUILD_DIR`/`BINDIRBASE`/`PKGDIRBASE`, `make` inside another command refused, missing directories refused | second `prestep.py` run in the same clone: no `git init`/`rm -Rf` (before: nrfx and cmsis deleted and re-fetched) |

After the fixes, `build_state.py` for both applications gives the same
modules, objects (44/44, 153/153), flags and link command as before the
fixes, so the byte-identical firmware results of §5/§6 stay valid.
Resolver parity (`2026-11-14-resolver.md`, 10 comparisons) unchanged.

Not fixed at first (fixed 2026-11-15, §8, except the verbatim shell
blocks): comment and continuation edge cases outside rules, `::=` and
computed assignment names, double expansion of `:=` values, approximate
`flavor`/`origin`, `$((…))` with Python division, double-colon and static
pattern rules, `FEATURES_MISSING`/`CONFLICTING` not reported by the
resolver's Python features check, 5 of 13 shell blocks run the host
command verbatim, and the timing in
`2026-11-14-resolver.md` compares Python on the host with Make in the
container.

## 8. Minor findings fixed (2026-11-15)

User decision (2026-11-15): fix the minor findings of §7 (subagent,
working tree). Each fix was compared with GNU Make 4.3 on a small test
Makefile (same output; the old code differed in each):
comment/continuation handling (comment removed after joining, `\#`,
`# … \`, tab lines outside rules, tab-indented conditionals in recipes),
assignments to computed names, `::=`, `!=`; flavor and origin per variable
(no double expansion of `:=` values, `$$` kept); computed names and
automatic variables in substitution references; relative includes against
CURDIR; double-colon and static pattern rules, pattern-rule choice;
`$((…))` arithmetic like dash, shell-block patterns anchored (4 injection
attempts rejected, all 21 real calls still matched);
FEATURES_MISSING/CONFLICTING/USED_BLACKLISTED reported like Make;
`wildcard`/`dir`/`notdir`/`basename`/`suffix` edge cases; MAKELEVEL and
MAKECMDGOALS in sub-makes.

Regression after the fixes: dependency-file translation 0 unsupported
(before 1); `--build` 6 unsupported (before 7); resolver parity 10/10;
`flags.py` variables identical to Make (hello-world, nrf52840dk); build
state of both applications in the container identical to the
firmware-checked state (§5/§6).

Still not modelled: trailing whitespace in values, re-expansion of
environment values in sub-makes, `$0` in `$(call)`, MAKECMDGOALS empty
instead of undefined at the top level.

## Not covered / limits

Two applications on `nrf52840dk` (hello-world, gnrc_networking);
C sources only (`SRCXX`, `ASMSRC`, `ASSMSRC`, `GENSRC` stop with a
message); the recipe runner is minimal (see §4, §7); generality beyond
the two applications is not shown; host toolchain probes
still run host tools; the generated CMake/Meson projects still list every
object (generated from the state, not hand-written).

## Reading [inference]

The full path from `riot-app.yaml` to the firmware image works without GNU
Make for this application: Make's knowledge (dependency rules, flags,
module layout, prerequisite recipes) is used as data and evaluated by
small Python tools, and the build itself runs in CMake or Meson. The data
is still written in Make syntax (translated, not yet migrated to a new
format); the translation coverage (99.8 % of the build files fully
parsed) is not yet a tool-independent format: the review (§7) counted 401
rules and 694 recipes kept as Make/shell text, 626 assignment and 359
condition expressions in Make syntax and 69 top-level calls among the
"structured" items. Converting the data once into a format independent of
Make is future work.
