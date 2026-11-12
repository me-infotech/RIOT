# AGENTS.md

RIOT is a single C codebase built **per application**; there is no root build,
package manager, workspace, or repo-wide test command. Over 200 supported
boards; `native`/`native32`/`native64` run on the host.

## Build

- Always build inside an app or test directory. Root `make` only prints a
  welcome (`Makefile:5`).
- `make -C examples/basic/hello-world BOARD=native64 all`
- `BOARD` defaults to `native` in every example and in
  `tests/Makefile.tests_common`; hardware builds need `BOARD=<board>`.
- Artifacts land in `bin/<board>/<app>.elf` per app. `bin/`, `build/` and
  `compile_commands.json` are gitignored — never commit them.
- `WERROR ?= 1` (`Makefile.include:249`): any compiler warning fails the build.
  Use `make ... WERROR=0` only for local exploration; CI builds with 1.
- `make help` lists all targets. Inspect instead of building:
  `just info-boards`, `make -C <app> BOARD=<b> info-build info-modules
  info-features-used info-buildsize`.
- `make compile-commands` in an app writes `${RIOTBASE}/compile_commands.json`
  for clangd.
- Toolchains come from the host. `BUILD_IN_DOCKER=1` uses the pinned
  `riot/riotbuild` image when a toolchain is missing.
- `make term` runs/attaches to the board (`BOARD=native` executes the host ELF);
  `make debug` needs `DEBUGGER`. Clean per app:
  `make -C <app> clean` / `distclean`.

## Tests

- Test apps are `tests/<area>/<name>/`, each including
  `tests/Makefile.tests_common`.
- `make -C tests/periph/gpio BOARD=native64 all test` builds, then runs every
  `<app>/tests/*` script through `dist/pythonlibs/testrunner` over a pty.
- Guards/selectors: `test/available` (honors `TEST_ON_CI_WHITELIST` /
  `TEST_ON_CI_BLACKLIST`), `test-with-config` (+ `check-config`), `test-as-root`
  (sudo). Many scripts need real hardware, `PORT`, or network namespaces and
  cannot pass on native.
- Native test builds set `NATIVE_AUTO_EXIT=1`; interactive sync modules are
  skipped for `native`, `native32`, `native64`.
- Running a script directly needs `PYTHONPATH=dist/pythonlibs`.
- `make static-test` is static analysis only, not the test suite.

## Static checks

- `make static-test` runs `dist/tools/ci/static_tests.sh` over the whole tree and
  diffs against `master` (`CI_BASE_BRANCH`). Missing tools (uncrustify,
  doxygen, vera++, spatch, codespell, shellcheck) make it fail, so it often
  cannot run on a plain dev machine.
- Targeted, much faster:
  `./dist/tools/uncrustify/uncrustify.sh --check`,
  `./dist/tools/whitespacecheck/check.sh master`,
  `./dist/tools/headerguards/check.sh`, `./dist/tools/licenses/check.sh`,
  `./dist/tools/doccheck/check.sh`, `./dist/tools/codespell/check.sh`,
  `./dist/tools/buildsystem_sanity_check/check.sh`.
- Blocking in CI: uncrustify, licenses/SPDX, whitespace, doccheck, headerguards,
  buildsystem sanity. Advisory only: clang-format, shellcheck.

## Code conventions (enforced)

- C11; no dynamic allocation, avoid floating point (`CODING_CONVENTIONS.md`).
- 80 columns target, 100 hard max; 4 spaces in C, tabs in `Makefile*`/`*.mk`;
  LF endings, no trailing whitespace, final newline (`.editorconfig`).
- New files need an SPDX header; public symbols need Doxygen `@brief` or
  `doccheck` fails.
- Header guards and `extern "C"` wrappers are checked by
  `dist/tools/headerguards` and `dist/tools/externc`.
- Naming: public API prefixed with its module name, otherwise lowercase with
  underscores, no CamelCase; typedefs end in `_t`; file-local functions are
  `static`; no-arg functions take `(void)`.

## Build-system rules (`buildsystem_sanity_check` enforces)

- App Makefiles must use `BOARD ?=`, must not define `APPLICATION` in test
  Makefiles, and must not enable features via `CFLAGS` (use
  `DEVELHELP ?= 1` or modules).
- Features belong only in `Makefile.features`; module dependencies only in
  `Makefile.dep`; `CFLAGS` changes in `Makefile.include`.
- Never export variables outside `makefiles/vars.inc.mk`; no `PSEUDOMODULES` in
  `Makefile.dep`; no `BOARD_INSUFFICIENT_MEMORY` (use `Makefile.ci`).
- `Makefile.ci` lists boards Murdock excludes for insufficient memory.
  Regenerate from inside the app dir with `make generate-Makefile.ci`; do not
  hand-edit.
- `features.yaml` generates `makefiles/features_existing.inc.mk`; after editing
  it run `just generate-features` in the repo root or CI's
  `check_features_existing_inc_mk_is_up_to_date.sh` fails.
- Modules live in `sys/`, `drivers/`, `cpu/`, `boards/`; each has a `Makefile`
  including `$(RIOTBASE)/Makefile.base`, plus `Makefile.dep`/`Makefile.features`
  entries where needed.
- `just doc` (root) regenerates `doc/doxygen/src/feature_list.md`; that file is
  generated, not hand-written.

## Workflow

- Commit subjects: `area: description` (e.g. `periph/timer: ...`). CI rejects
  markers listed in `dist/tools/pr_check/no_merge_keywords`.
- Murdock CI is configured by `.murdock.yml`; `ci_skip` / `murdock_skip` in a
  commit message skips it.
- Run `make static-test` (or the targeted scripts above) before proposing a PR.
- Use `git status` before finishing: app builds leave `bin/`, `bindist/`,
  `Makefile.ci` and `dependencies_info_*` behind; only `Makefile.ci` is a real
  tracked file when intentionally changed.
