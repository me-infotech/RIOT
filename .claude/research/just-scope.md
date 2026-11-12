# just scope — which targets may live in the justfile

Status: 2026-11-12, user rule (decision log D17) plus source review of all 57
group-1 targets (D18). This file is the **single source of truth** for what
the task layer (`just`) may contain. Agents and skills reference it; do not
re-derive the scope from the workbook dispositions.

## The rule (user, 2026-11-12)

> just only contains targets that have nothing to do with Make, with
> artifacts, with runtime state, or with the artifact lifecycle. That is the
> main goal of the migration: move responsibilities **out of** Make, not
> build a new surface **on top of** Make.

Operationally, a target may go to just only if **all** of these hold:

1. **Group 1** in `riot_all_make_targets.xlsx` (not 2A, 2B, 2C, 3). External
   host tools (doxygen, npm, riotgen, Python scripts) are allowed; external
   services that need board/app context or artifacts (IoT-LAB, OpenVisualizer,
   package downloads) are not — they belong to groups 2A/2B.
2. **No Make in just:** the recipe never calls `make`, `$(MAKE)`, a private
   `_helper` Make target, or a script whose purpose is to run Make. The logic
   is re-implemented in the recipe (shell/Python), not delegated.
3. **No Make-computed input:** every input comes from repository files,
   environment variables or recipe parameters — never from Make's variable
   resolution (`BOARD`, `CPU`, `USEMODULE`, `FEATURES_*`, `BINDIR`, `ELFFILE`).
4. **No artifact contact:** it does not read, create inside the build graph,
   or delete build/package/tool artifacts.

Direction of calls:

| Call | Allowed? |
|---|---|
| `make <t>` → `just <t>` (thin forwarding for group-1 targets) | **No** (D20) — migrated targets are removed from Make; callers use just |
| `just <r>` → `make …` (incl. `_helper`) | **Never** |
| groups 2A/2B/2C/3 in the justfile, in any form | **Never** — they go to the build layer (CMake+Ninja, compared with Meson+Ninja; roadmap P6) |

The workbook dispositions `MIGRATE`/`BRIDGE` for 2A/2B/2C/3 targets
(waves 2 and 3, 42 targets) and the pilot's just → `_helper` bridges
contradict this rule. The workbook stays read-only; the rule here overrides
its dispositions for the task layer.

## Result of the source review (RIOT `0be9299ca9`)

### A — just, pure (28; workbook `MIGRATE`, wave 1)

| Targets | Source | Note |
|---|---|---|
| `info-boards`, `info-emulated-boards` | `makefiles/boards.inc.mk:20,32` | directory scan; sort byte order (`LC_ALL=C sort -u`), no trailing space |
| `info-applications` | `makefiles/app_dirs.inc.mk:26` | `find` over app dirs + `app_dirs.blacklist` |
| `list-ttys` | `Makefile.include:823` | `dist/tools/usb-serial/ttys.py` |
| `welcome` | `Makefile:81` | static text |
| `print-versions` | `Makefile:26` | script reports `make --version` and Make's shell — Make as an *inspected host tool*, not Make logic; allowed, drop those lines once Make is gone |
| `doc`, `doc-man`, `doc-latex` | `Makefile:9-13` → `doc/doxygen/Makefile` | today **two Make levels** (`$(MAKE) -C doc/doxygen`); the just recipe must contain the doxygen pipeline itself: `features_yaml2mx.py`, `STRIP_FROM_INC_PATH_LIST` via `git ls-tree`, `generate-changelog.py`, `riot.doxyfile` + `GENERATE_*` |
| `html`, `man`, `latex`, `check`, `doxygen-version`, `graphviz-check` | `doc/doxygen/Makefile:62-118` | `src/changelog.md` is a Make file rule → in just always regenerate (cheap) |
| `doc-starlight`, `build`, `dev`, `preview` | `Makefile:15`, `doc/starlight/Makefile:12-21` | npm; prerequisite `install` = `npm ci` (doc toolchain, not a build artifact) |
| `integrate_outside_files`, `code_of_conduct`, `coding_conventions`, `coding_conventions_cpp`, `contributing`, `governance`, `lostandfound`, `security`, `unittests` | `doc/starlight/Makefile:30-75` | `sed` + template copies |

Name collisions: `build`, `check`, `install`, `dev`, `preview` and other
generic names → in just, recipes from `doc/doxygen/Makefile` and
`doc/starlight/Makefile` are named `doxygen-<target>` / `starlight-<target>`
(e.g. `doxygen-html`, `starlight-build`); `doxygen-version` and
`graphviz-check` keep their names. Starlight `install` (npm ci) stays a Make
target (name is group 2C); just runs the same steps as recipe
`starlight-install`, which the Make target calls.

Pass-through (historical, while forwards existed; obsolete since D20): in an
application context Make exports `RIOTBASE`, `RIOTBOARD`,
`EXTERNAL_BOARD_DIRS`, `RIOTTOOLS` (paths normalised to absolute). These are
user inputs / repository locations, not resolved state; just reads them from
the environment. Make-*derived* values (`BOARDSDIRS` from a Makefile,
`APPLICATION_DIRS`, filtered `BOARDS`) are never passed on.

**Status 2026-11-12:** A+B implemented (roadmap P3, uncommitted) — see
`test-logs/2026-11-12-p3-group1-just.md`.

Note (historical, forwards removed by D20): `export BOARDS ?=` (target-specific, `makefiles/app_dirs.inc.mk`)
exports Make's board list for every root target in GNU Make 4.3. The
`info-boards` forward removes it (`env -u BOARDS` unless the user set it);
the other forwarded recipes do not read `BOARDS`.

### B — just, re-classified from `OUT OF SCOPE` (8)

| Targets | Source | Why just is fine |
|---|---|---|
| `generate-board`, `generate-driver`, `generate-example`, `generate-module`, `generate-pkg`, `generate-test` | `makefiles/tools/riotgen.inc.mk:17-21` | `RIOTBASE=<root> riotgen <kind> -i`; external host tool, only input is the repo root |
| `riotgen-installed` | `riotgen.inc.mk:8` | `command -v riotgen` |
| `generate-features` | `Makefile:29` | `features_yaml2mx.py features.yaml --output-makefile …`; recipe is Make-free. Its *output* is a Make include (consumer = config layer); `check_features_existing_inc_mk_is_up_to_date.sh` calls `make generate-features` and must switch to `just` when migrated |

### C — stay in Make for now (2; user decision 2026-11-12, D18)

| Target | Finding |
|---|---|
| `doc-ci` | `doc/doxygen/Makefile:83` runs `$(MAKE) -C dist/tools/doxygen all`, which downloads doxygen **or builds it from source** (`git clone` + `cmake` + `make`; on non-x86_64 hosts and for `latest`). Host-tool compilation is group 3 by the workbook's own rule. Pure just only if doxygen provisioning is split off. |
| `static-test` (root) | `static_tests.sh` sub-checks run `make -C makefiles/tests/feature_resolution`, `make -C makefiles/tests/boards_supported` and `make generate-features` — tests of Make's resolution. Indirect Make dependency. (The same name in `tests/build_system/xfa` depends on `$(ELFFILE)` = group 3.) |

### D — not just; workbook group 1 is questionable (4)

| Target | Finding | Suggested group |
|---|---|---|
| `download_binary` | `dist/tools/doxygen/Makefile:81`: prerequisite `distclean` (deletes tool artifacts), inputs `PKG_VERSION`/`PKG_SHA512` from the calling Make, `BIN_PKG_*` computed by Make at parse time; workbook rule "tool provisioning without compilation = 2A" | 2A (+2C prerequisite) |
| `bin` | `mkdir bin` only as prerequisite of host-tool builds (`all: bin bin/uhcpd`) in `dist/tools/{uhcpd,benchmark_udp,zep_dispatch}` | part of 3 |
| `mock_suit_sec` | `SUIT_SEC` stub that suppresses key generation in a test-app build | part of 3 |
| `warn_release_tests` | appended to `BUILDDEPS` and `TERMDEPS` — a hook in the build/term graph | part of 3 / 2B |

### E — stay in Make (15; user decision)

`test-chars_from`, `test-chars_upto`, `test-ensure_value`,
`test-ensure_value-negative`, `test-exported-variables`, `test-is_number`,
`test-lowercase`, `test-max_number`, `test-memoized-variables`,
`test-split_chars`, `test-uppercase`, `test-uppercase_and_underscore`,
`test-version_is_greater`, `test-version_is_greater_or_equal`,
`test-version_tuple` — they test GNU Make functions themselves
(`makefiles/utils/test-*.mk`) and disappear with Make.

### Counts

| | Count |
|---|---:|
| Group 1 total | 57 |
| A + B (just, decided) | **36** |
| C (stay in Make for now) | 2 |
| D (not just, re-classification suggested) | 4 |
| E (stay in Make) | 15 |

## Where groups 2A/2B/2C/3 go

Not to just. Target: build layer (CMake + Ninja, compared hands-on with
Meson + Ninja in roadmap P6) and the configuration layer (resolved state
exported by the resolver). Examples: `info-modules`/`info-features-*` become
configure-time output of the build tool; `clean` becomes the build tool's
clean; `term`/`debug`/`flash` become custom targets on the artifact graph.
Until then they stay **Make-native and untouched**.
