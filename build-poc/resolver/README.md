# resolver — dependency resolution without Make (roadmap P6, D25)

Resolves the modules, packages and features of a RIOT application from data
instead of Make. Decisions (D25): rules are data translated from the
existing make files; they are evaluated in Make's order; scope of the proof
of concept: hello-world and gnrc_networking.

| File | Purpose |
|---|---|
| `translate_deps.py` | translates every `Makefile.dep`, `Makefile.features`, `*.dep`, `Makefile.default` and the plain-rule pipeline files (`makefiles/defaultmodules_*.inc.mk`, `features_modules.inc.mk`), plus every file they include, into an ordered rule list (JSON) and counts what it cannot translate |
| `makeexpr.py` | evaluator for the Make functions used in RIOT's make files (text, file name, `foreach`, `call` with parameters, `eval`, `file`, `wildcard`, `shell` through hooks, substitution references, computed names); known gaps: see the test log §7/§8 |
| `resolver.py` | evaluates the rules for `riot-app.yaml` + board in Make's order (features, default modules, features check, fixpoint over `Makefile.dep`, finalisation); the features check (`makefiles/features_check.inc.mk`) is implemented in Python |

Rule format (`riot-dep-rules/0`): per file a list of items, each one of
`{"if": cond, "then": [...], "else": [...]}`, `{"assign": VAR, "op":
"+=|:=|?=|=", "words"|"expr": ...}`, `{"include"|"include_expr": ...,
"optional": bool}`, `{"message": "error|warning|info", "text": ...}`.
Conditions: `any`/`none` (`$(filter …,$(VAR))` non-empty/empty),
`any_out`/`none_out` (`filter-out`), `eq`/`ne`, `def`/`undef`, and `expr`
(fallback: two Make expressions compared).

```sh
build-poc/resolver/translate_deps.py <riot> rules.json
build-poc/resolver/resolver.py <riot> rules.json <app>/riot-app.yaml nrf52840dk
```

## Build without Make (D26)

| File | Purpose |
|---|---|
| `flags.py` | evaluates `Makefile.include` as data (CFLAGS, INCLUDES, LINKFLAGS, …); `$(shell …)` through named blocks (`SHELL_BLOCKS`; 5 of them run the host command verbatim) |
| `submake.py` | the per-module sub-makes (DIRS recursion, package `all` recipes): objects, sources, exact compile flags |
| `prestep.py` | minimal recipe runner for `BUILDDEPS` (package preparation, vendor headers, `riotbuild.h`, `preprocessor_successor.h`): time stamps, order-only prerequisites, Make's exported environment, target-specific variables; commands run unchanged; recursive `$(MAKE)` is evaluated from the rules; refuses `rm -r/-f` outside the build directories |
| `build_state.py` | `resolved-state.json` for `gen_cmake.py` / `gen_meson.py`, without Make |

```sh
build-poc/resolver/translate_deps.py <riot> rules.json --build
build-poc/resolver/prestep.py <riot> rules.json <app>/riot-app.yaml nrf52840dk
build-poc/resolver/build_state.py <riot> rules.json <app>/riot-app.yaml nrf52840dk > state.json
build-poc/gen_cmake.py state.json cmake-src   # or gen_meson.py
```

Requirements: Python 3, PyYAML. Not modelled: values set in the
environment or on the command line, `EXTERNAL_MODULE_DIRS`, Kconfig.
Results: `.claude/research/test-logs/2026-11-14-resolver.md`,
`.claude/research/test-logs/2026-11-14-build-without-make.md`.
