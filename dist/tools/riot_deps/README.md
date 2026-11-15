# riot_deps — dependency rules in YAML (decision D27)

Each directory that has a `Makefile.dep` can hold its dependency rules in
`deps.yaml` (`Makefile.<x>.dep` ↔ `<x>.deps.yaml`). The YAML is the
authoritative source; the `Makefile.dep` next to it is **generated** and
checked in, so Make keeps working during the transition (pattern of
`features.yaml` → `makefiles/features_existing.inc.mk` and
`riot-app.yaml` → `riot-app.inc.mk`). The resolver in `build-poc/resolver`
reads the YAML directly.

```sh
just generate-deps                                   # regenerate all Makefile.dep
dist/tools/riot_deps/riot_deps.py generate --check --all   # CI (static_tests.sh)
dist/tools/riot_deps/riot_deps.py export <Makefile.dep>…   # one-time conversion
```

Format (`schema_version: 1`, ordered `rules:` list): `add: {VAR: [words]}`,
`assign: {var, op, value}`, `include: [paths]` (`optional: true` for
`-include`), `message: {level, text}`, `when: {VAR: {any|none|any_except|
none_except: [patterns]}}` / `{VAR: {equals|not_equals: value}}` /
`{VAR: {defined: bool}}` with `then:`/`else:`, and `comment:` (kept in the
generated file). What cannot be expressed this way stays a Make expression
under the key `make_expr` (or `include_make_expr`), so it is visible.

Scope of the proof of concept: the 30 dependency files hello-world and
gnrc_networking read on `nrf52840dk` (17 + 13); all other `Makefile.dep`
are unchanged. Edit the YAML, never
the generated `Makefile.dep`. Requires Python 3 and PyYAML; uses the
translator of `build-poc/resolver` for the one-time export.
