# Test log — Roadmap P4: configuration layer PoC (2026-11-13)

## Scope

D21 implemented in the working tree of `RIOT_Test` (HEAD `8a39e8ebb9`,
uncommitted): `riot-app.yaml` is the source of the application inputs of
`examples/basic/hello-world` (HW) and `examples/networking/gnrc/networking`
(GN); `riot-app.inc.mk` is generated from it and included by the app
`Makefile`. Boards: `native64`, `native` only.

| File | State |
|---|---|
| `dist/tools/riot_app_config/riot-app.schema.json` | new (JSON Schema 2020-12) |
| `dist/tools/riot_app_config/riot_app_config.py` | new (generator, `--all`, `--check`) |
| `dist/tools/riot_app_config/README.md` | new |
| `dist/tools/ci/check_riot_app_config_up_to_date.sh` | new (not wired into `static_tests.sh`) |
| `just/generate.just` | recipe `generate-app-config` added |
| `examples/basic/hello-world/{Makefile,riot-app.yaml,riot-app.inc.mk}` | Makefile reduced; 2 new files |
| `examples/networking/gnrc/networking/{Makefile,riot-app.yaml,riot-app.inc.mk}` | Makefile reduced (USE_ZEP condition and post-include stay); 2 new files |

## Environment

GNU Make 4.3, just 1.59.0, Python 3.12.3, PyYAML 6.0.1, jsonschema 4.10.3
(`python3-jsonschema`, installed by the user during the session), gcc 13.3.0,
Linux 7.0.0-43-generic x86_64, `getconf LONG_BIT` = 64.

Scratch directory (`$S`):
`/tmp/claude-1000/-home-mohammadjavad--claude-spares-spare-IvD0aY/3fe3e886-6912-4592-a33e-c56651c646b1/scratchpad`

- `$S/ref`: `git clone --shared RIOT_Test` + `git checkout 8a39e8ebb9` (unchanged reference)
- `$S/newclone`: same, plus the 11 changed/new files copied with `cp --parents`
  and `git add -N .` (so that `git grep`-based checks see the new files)

Baseline check: `cd .claude/research/p4-baseline && sha256sum -c SHA256SUMS` → all OK.

## 1. Generation

```sh
cd RIOT_Test
python3 -c "import jsonschema, json; jsonschema.Draft202012Validator.check_schema(json.load(open('dist/tools/riot_app_config/riot-app.schema.json')))"   # schema ok
dist/tools/riot_app_config/riot_app_config.py --all          # rc=0
just generate-app-config                                     # rc=0, no change
dist/tools/riot_app_config/riot_app_config.py --check --all  # rc=0
dist/tools/ci/check_riot_app_config_up_to_date.sh            # rc=0
```

Uncommented `cflags:` variant of the GN yaml (scratch copy) validates and
renders `CFLAGS += -DCONFIG_GNRC_IPV6_STATIC_LLADDR='"fe80::cafe:cafe:cafe:1"'`
and `CFLAGS += -DCONFIG_GNRC_RPL_DODAG_CONF_OPTIONAL_ON_JOIN`.
`develhelp: 1.0` (JSON Schema counts it as integer) renders `DEVELHELP ?= 1`.

## 2. Gate P4 (info-build-json + info-debug-variable-*)

Script `$S/gate.sh <tree> <outdir>` reproduces every file of `p4-baseline/`
(same commands as `p4-baseline/commands.txt`, same 43 variables) and replaces
the tree path by `/home/mohammadjavad/Documents/RIOT`:

```bash
#!/bin/bash
# usage: gate.sh <tree> <outdir>  -- reproduces p4-baseline files for <tree>,
# normalising the tree path to /home/mohammadjavad/Documents/RIOT
T=$1; O=$2; mkdir -p "$O"; B=/home/mohammadjavad/Documents/RIOT_Test/.claude/research/p4-baseline
norm() { sed "s#$T#/home/mohammadjavad/Documents/RIOT#g"; }
unset BOARD CFLAGS DEVELHELP QUIET WERROR USEMODULE USE_ZEP
run() { # name app board
  make --no-print-directory -C "$T/$2" BOARD=$3 info-build-json 2>"$O/$1.stderr.raw" | norm > "$O/$1.info-build-json.json"
  norm < "$O/$1.stderr.raw" > "$O/$1.stderr.txt"; rm "$O/$1.stderr.raw"
}
run hello-world.native64 examples/basic/hello-world native64
run hello-world.native examples/basic/hello-world native
run gnrc_networking.native64 examples/networking/gnrc/networking native64
VARS=$(cut -f2 $B/info-debug-variables.txt | awk '!s[$0]++')
: > "$O/info-debug-variables.txt"
for c in hello-world.native64:examples/basic/hello-world:native64 hello-world.native:examples/basic/hello-world:native gnrc_networking.native64:examples/networking/gnrc/networking:native64; do
  IFS=: read n a b <<<"$c"
  for v in $VARS; do
    printf '%s\t%s\t%s\n' "$n" "$v" "$(make --no-print-directory -C "$T/$a" BOARD=$b info-debug-variable-$v 2>/dev/null | norm)" >> "$O/info-debug-variables.txt"
  done
done
```

```sh
$S/gate.sh /home/mohammadjavad/Documents/RIOT_Test $S/new
$S/gate.sh $S/ref $S/refout
for f in <7 files>; do cmp p4-baseline/$f $S/new/$f; cmp $S/refout/$f $S/new/$f; done
```

| File | vs. baseline | vs. clean clone 8a39e8ebb9 |
|---|---|---|
| `hello-world.native64.info-build-json.json` | identical | identical |
| `hello-world.native.info-build-json.json` | identical | identical |
| `gnrc_networking.native64.info-build-json.json` | identical | identical |
| `*.stderr.txt` (3) | identical | identical |
| `info-debug-variables.txt` (43 vars × 3, incl. APPLICATION, BOARD, RIOTBASE, DEVELHELP, QUIET, WERROR, USEMODULE, USEPKG, FEATURES_*, CFLAGS, EXTERNAL_*_DIRS, USE_ZEP, ZEP_PORT_BASE, BINDIR) | identical | identical |

`git status --short --ignored` of both app directories before/after the runs:
identical (the targets write nothing).

Only expected difference: `MAKEFILE_LIST` gains one entry
(`.../riot-app.inc.mk` at position 2) —
`make -C <app> BOARD=native64 info-debug-variable-MAKEFILE_LIST` in `$S/ref`
vs `$S/newclone`, GN: `1a2 > T/examples/networking/gnrc/networking/riot-app.inc.mk`.

## 3. Precedence (environment / command line)

Script `$S/prec.sh <tree>`: 25 cases, each printing BOARD APPLICATION RIOTBASE
DEVELHELP QUIET WERROR USEMODULE USE_ZEP ZEP_PORT_BASE EXTERNAL_BOARD_DIRS
CFLAGS BINDIR (tree path replaced by `<TREE>`):

```bash
#!/bin/bash
# usage: prec.sh <tree>  -- precedence cases; prints normalised results
T=$1
unset BOARD CFLAGS DEVELHELP QUIET WERROR USEMODULE USE_ZEP ZEP_PORT_BASE APPLICATION EXTERNAL_BOARD_DIRS RIOTBASE
HW=examples/basic/hello-world; GN=examples/networking/gnrc/networking
VARS="BOARD APPLICATION RIOTBASE DEVELHELP QUIET WERROR USEMODULE USE_ZEP ZEP_PORT_BASE EXTERNAL_BOARD_DIRS CFLAGS BINDIR"
tg() { for v in $VARS; do echo -n "info-debug-variable-$v "; done; }
c() { # label app env-assignments -- make-args
  local label=$1 app=$2; shift 2; local envs=(); while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  echo "### $label"
  env "${envs[@]}" make --no-print-directory -C "$T/$app" "$@" $(tg) 2>&1 | sed "s#$T#<TREE>#g"
}
c "HW default (no BOARD)" $HW --
c "HW env BOARD=native" $HW BOARD=native --
c "HW cmd BOARD=native" $HW -- BOARD=native
c "HW env DEVELHELP=0" $HW DEVELHELP=0 -- BOARD=native64
c "HW cmd DEVELHELP=0" $HW -- BOARD=native64 DEVELHELP=0
c "HW env QUIET=0" $HW QUIET=0 -- BOARD=native64
c "HW cmd QUIET=0" $HW -- BOARD=native64 QUIET=0
c "HW cmd APPLICATION=foo" $HW -- BOARD=native64 APPLICATION=foo
c "HW env APPLICATION=foo" $HW APPLICATION=foo -- BOARD=native64
c "HW env RIOTBASE=tree" $HW RIOTBASE=$T -- BOARD=native64
c "HW env CFLAGS=-DFOO" $HW CFLAGS=-DFOO -- BOARD=native64
c "HW cmd CFLAGS=-DFOO" $HW -- BOARD=native64 CFLAGS=-DFOO
c "HW env USEMODULE=ztimer" $HW USEMODULE=ztimer -- BOARD=native64
c "HW cmd USEMODULE+=ztimer" $HW -- BOARD=native64 USEMODULE+=ztimer
c "GN env USEMODULE=ztimer" $GN USEMODULE=ztimer -- BOARD=native64
c "GN cmd USEMODULE+=ztimer" $GN -- BOARD=native64 USEMODULE+=ztimer
c "GN cmd USEMODULE=shell" $GN -- BOARD=native64 USEMODULE=shell
c "GN env USE_ZEP=1" $GN USE_ZEP=1 -- BOARD=native64
c "GN cmd USE_ZEP=1" $GN -- BOARD=native64 USE_ZEP=1
c "GN env ZEP_PORT_BASE=20000" $GN ZEP_PORT_BASE=20000 -- BOARD=native64
c "GN cmd ZEP_PORT_BASE=20000" $GN -- BOARD=native64 ZEP_PORT_BASE=20000
c "GN env DEVELHELP=0" $GN DEVELHELP=0 -- BOARD=native64
c "GN env EXTERNAL_BOARD_DIRS=/nonexistent" $GN EXTERNAL_BOARD_DIRS=/nonexistent -- BOARD=native64
c "GN cmd EXTERNAL_BOARD_DIRS=" $GN -- BOARD=native64 EXTERNAL_BOARD_DIRS=
c "GN env BOARD=native" $GN BOARD=native --
```

```sh
$S/prec.sh RIOT_Test > $S/prec.new.txt; $S/prec.sh $S/ref > $S/prec.ref.txt
cmp $S/prec.new.txt $S/prec.ref.txt     # identical (330 lines, 25 cases)
```

Spot checks that the overrides took effect (same in both trees):
`GN cmd USE_ZEP=1` → USEMODULE contains `socket_zep`; `HW env DEVELHELP=0`
→ `0`; `HW cmd APPLICATION=foo` → `foo`; `GN cmd USEMODULE=shell` → `shell`.

## 4. Negative tests

Generator on invalid scratch copies of the HW yaml
(`riot_app_config.py $S/neg/<case>/riot-app.yaml`); every case rc=1 and no
`riot-app.inc.mk` written:

| Case | Message (abridged) |
|---|---|
| unknown key `usemodules` | `(top): Additional properties are not allowed ('usemodules' was unexpected)` |
| `develhelp: yes` (YAML 1.1 bool) | `develhelp: True is not of type 'integer'` |
| `develhelp: 2` | `develhelp: 2 is not one of [0, 1]` |
| `develhelp: "1"` | `develhelp: '1' is not of type 'integer'` |
| `board: [native]` | `board: ['native'] is not of type 'string'` |
| `usemodule: [shell, "$(FOO)"]` | `usemodule/1: '$(FOO)' does not match ...` |
| `usemodule: [shell, shell]` | `has non-unique elements` |
| duplicate key `quiet` | `duplicate key 'quiet' (line 22)` |
| `app_defaults: {BOARD: ...}` | `'BOARD' should not be valid under {'enum': [...]}` |
| `app_defaults: {use_zep: 0}` | `'use_zep' does not match '^[A-Z][A-Z0-9_]*$'` |
| `external_board_dirs: [{riotbase: /abs}]` | `does not match ...` (absolute path) |
| entry with `riotbase` and `appdir` | `has too many properties` |
| no `application` | `'application' is a required property` |
| YAML syntax error | PyYAML parser error with line/column |
| top level is a list | `(top): ['a list'] is not of type 'object'` |
| jsonschema not importable (`sys.modules['jsonschema'] = None`, `runpy`) | `error: the Python module 'jsonschema' is needed ... (Debian/Ubuntu: package python3-jsonschema)`, rc=1 |

CI check on manipulated files in `RIOT_Test` (backup in `$S`, restored with
`cp`, then `cmp` against backup and check rc=0 → restored and clean):

| Case | `check_riot_app_config_up_to_date.sh` |
|---|---|
| N1 `DEVELHELP ?= 0` in HW `riot-app.inc.mk` | rc=1, `...hello-world/riot-app.inc.mk: outdated`; file not rewritten |
| N2 extra `USEMODULE += xtimer` in GN fragment | rc=1, outdated |
| N3 extra blank line at end of GN fragment | rc=1, outdated |
| N4 HW fragment removed | rc=1, `missing`; `make ... info-debug-variable-APPLICATION` fails too (rc=2, `/Makefile.include: No such file`) |
| N5 HW yaml `quiet: 0`, fragment not regenerated | rc=1, outdated |
| N6 HW yaml `quiet: loud` | rc=1, schema error; `just generate-app-config` also rc=1 |

## 5. Repository checks

| Command | Where | Result |
|---|---|---|
| `just --fmt --check --unstable` | RIOT_Test, `$S/newclone` | rc=0 |
| `git diff --check -- examples just dist` | RIOT_Test | rc=0 |
| `git diff --check` (whole tree) | RIOT_Test | rc=2, only pre-existing `.claude/research/decision-log.md:330: new blank line at EOF` (already before this work) |
| `git diff --check` | `$S/newclone` (only P4 files) | rc=0 |
| `ENABLE_DOCKER_PINNING_TEST=0 dist/tools/buildsystem_sanity_check/check.sh` | RIOT_Test (before and after), `$S/newclone` with `git add -N` | rc=0 |
| `dist/tools/ci/check_features_existing_inc_mk_is_up_to_date.sh` | RIOT_Test, `$S/newclone` | rc=0 |
| `dist/tools/ci/check_riot_app_config_up_to_date.sh` | RIOT_Test, `$S/newclone` | rc=0 |
| flake8 / pylint / shellcheck | — | not installed, not run; line length ≤ 119 (flake8.cfg) checked with awk |

Note: the sanity check uses `git grep`, so in RIOT_Test it does not see the
untracked new files; hence the extra run in `$S/newclone` with `git add -N`.
`dist/tools/licenses/check.sh` only checks C/assembler files (`FILEREGEX`), not
relevant here; stopped.

## 6. Build (optional)

```sh
make --no-print-directory -C $S/ref/examples/basic/hello-world BOARD=native64 all -j8       # rc=0
make --no-print-directory -C $S/newclone/examples/basic/hello-world BOARD=native64 all -j8  # rc=0
nm <tree>/examples/basic/hello-world/bin/native64/hello-world.elf
```

`nm` output (275 lines, including addresses) byte-identical between both
trees; size `text 29078 data 1080 bss 59128` in the new tree.

## Result

Gate P4 met for HW/native64, HW/native, GN/native64: resolved state and all
43 inspected variables identical to the baseline and to the clean clone;
precedence of environment and command line unchanged (25 cases); negative
tests fail as required. Nothing committed.

---

## Follow-up 2026-11-13: Nachtrag D21 and review findings

Working tree as above (HEAD `8a39e8ebb9`, uncommitted). Environment
unchanged (GNU Make 4.3, just 1.59.0, Python 3.12.3, PyYAML 6.0.1,
jsonschema 4.10.3).

### Changes

| Item | Change |
|---|---|
| A1 / Major 2 | `static_tests.sh`: `should_run riot_app_config ./dist/tools/ci/check_riot_app_config_up_to_date.sh` (after the features check), `DEPS[...]="python3"`. `test_selection.sh`: `TEST_PATHS[riot_app_config]="*riot-app.yaml *riot-app.inc.mk dist/tools/riot_app_config/* dist/tools/ci/check_riot_app_config_up_to_date.sh"`; `any_make_files` += `*riot-app.inc.mk`; `any_build_files` += `*riot-app.yaml` (so feature-resolution and boards-supported checks run on YAML/fragment changes). jsonschema documented as CI-image prerequisite (tool README, MIGRATION.md "Prerequisite") |
| A2 | `schema_version` required, schema `const: 1`; generator checks it before the schema with its own message. **Not emitted** into `riot-app.inc.mk` (not even as a comment) — fragments stay byte-identical |
| A3 / Minor 1 | App Makefiles: `RIOT_APP_CONFIG_MK := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/riot-app.inc.mk`, captured as first statement, `$(error ... missing: run 'just generate-app-config' in the RIOT root)` if absent, then `include $(RIOT_APP_CONFIG_MK)`. With `make -C`/`make` in the app dir the path equals the former `$(CURDIR)/riot-app.inc.mk` (same `MAKEFILE_LIST`) |
| Major 1 | Loader `_StrictLoader`: int constructor accepts only `^-?(0\|[1-9][0-9]*)$`; every other YAML 1.1 int form (octal, hex, binary, sexagesimal, `_`, `+`, leading zero) → error; float constructor → always error; bool constructor → error with hint (Nit 2). `_text()` float workaround removed |
| Minor 2 | `UnicodeDecodeError`/`OSError` on read (YAML, schema, existing fragment) → `ConfigError`; fragment compared as bytes; write via `tempfile.NamedTemporaryFile` in the same directory + `os.replace`, mode of an existing file kept (new file: `0666 & ~umask`), temp file removed on failure |
| Minor 3 | All given files (or `--all`) are loaded/validated first; every error reported; rc=1 at the end; in write mode nothing is written if any file failed |
| Minor 4 | `app_defaults` deny list extended (44 names, incl. CPU, CPU_MODEL, CFLAGS, CXXFLAGS, LINKFLAGS, LDFLAGS, DEFAULT_MODULE, BOARD_INSUFFICIENT_MEMORY, FEATURES_PROVIDED, USEMODULE, USEPKG, all key variables); `cflags` items `not: pattern ^-DDEVELHELP` (same prefix as the sanity rule); `application` optional; sanity-check pathspecs `**/riot-app.inc.mk` (BOARD =, BOARD_INSUFFICIENT_MEMORY, -DDEVELHELP) and `tests/**/riot-app.inc.mk` (APPLICATION). Error text for `not` rules shortened (no enum dump) |
| Minor 5/6, Nit 4 | MIGRATION.md: new section "Configuration layer (roadmap P4)" (rule, files, inputs/precedence, adding an app, verification, known limits incl. `rpl.mdx` note), Prerequisite, Onboarding; README: regenerate after editing, make does not read the YAML; just-scope.md F and decision log Nachtrag: just itself never reads the app config, the generator recipe runs a Python tool that does |
| Nit 1 | input basename must be `riot-app.yaml` |
| Nit 5 | `check_riot_app_config_up_to_date.sh` calls the Python tool directly by design (not via `just`): CI needs no just for this check, and the features check pattern is kept (Python generator, shell wrapper) |

### Commands and results

`$S` = scratch directory as above. `$S/newclone` was recreated:
`git clone --shared RIOT_Test` + `checkout 8a39e8ebb9` + `cp --parents -p` of
the 15 P4 files (MIGRATION.md, 3 CI/sanity scripts, 4 tool files, 2 Makefiles,
4 YAML/fragments, `just/generate.just`) + `git add -N .`.

1. Generation: `riot_app_config.py --all` rc=0 (no change, fragments
   untouched), `--check --all` rc=0, `just generate-app-config` rc=0,
   `check_riot_app_config_up_to_date.sh` rc=0. Schema meta-check ok.
2. Gate: `$S/gate.sh RIOT_Test $S/new2`, `$S/gate.sh $S/newclone $S/nc2`;
   `sha256sum -c SHA256SUMS` in `p4-baseline` → 0 failures. All 7 files
   (`*.info-build-json.json` ×3, `*.stderr.txt` ×3, `info-debug-variables.txt`,
   129 lines = 43 vars × 3) `cmp`-identical to the baseline, to `$S/nc2` and
   to `$S/refout` (clean 8a39e8ebb9).
3. `MAKEFILE_LIST` (`make -C <app> BOARD=native64 info-debug-variable-MAKEFILE_LIST`):
   new tree = ref + `T/<app>/riot-app.inc.mk` at position 2 (absolute path,
   as before the change).
4. Precedence: `$S/prec.sh RIOT_Test` and `$S/prec.sh $S/newclone` vs
   `$S/prec.ref.txt` → identical (330 lines, 25 cases).
5. Invocation variants (ref vs newclone; 10 variables APPLICATION BOARD
   RIOTBASE USEMODULE USE_ZEP ZEP_PORT_BASE EXTERNAL_BOARD_DIRS DEVELHELP
   QUIET APPDIR, `BOARD=native64`, tree path normalised), both apps:
   `cd <app> && make` = `make -C <app>` from `$S/elsewhere` (md5 equal, and
   equal between trees); `cd $S/elsewhere && make -f <abs>/Makefile
   RIOTBASE=<tree>` rc=0 and identical to ref (GN: full USEMODULE list,
   ZEP_PORT_BASE 17754, EXTERNAL_BOARD_DIRS → fragment found). Without
   `RIOTBASE` both trees fail identically (`$(CURDIR)/../../../Makefile.include`
   not found; only Makefile line numbers differ) — unchanged behaviour,
   documented as limit.
6. Negative tests, new (`$S/neg2.sh RIOT_Test`, scratch copies of the HW
   yaml; all rc=1 and no fragment written unless noted):

| Case | Message (abridged) |
|---|---|
| `017754`, `0x10`, `1:30`, `0b11`, `1_000`, `+1`, `00` | `'<v>' (line N): YAML 1.1 reads this as a number in another notation ...; write a plain decimal integer, or quote the value` |
| `1.0`, `develhelp: 1.0`, `.inf`, `1:30.5` | `'<v>' (line N): floating point numbers are not allowed ...` |
| `develhelp: yes`, `USE_ZEP: off` | `'yes' (line 21): YAML 1.1 reads yes/no/on/off/true/false as a boolean ...; write 0 or 1 for a flag, or quote` |
| `"0x10"` quoted, `-12` | rc=0 (accepted) |
| no `schema_version` | `schema_version is missing; add 'schema_version: 1'` |
| `schema_version: 2` / `"1"` | `schema_version 2 is not supported; this generator reads version 1` / `'1' ...` |
| no `application` | rc=0 (optional) |
| `app_defaults` CPU / LDFLAGS / BOARD_INSUFFICIENT_MEMORY / FEATURES_PROVIDED | `app_defaults: 'CPU' is not allowed here (see the key's description in riot-app.schema.json)` |
| `cflags: [-DDEVELHELP]`, `[-DFOO, -DDEVELHELP=1]` | `cflags/0: '-DDEVELHELP' is not allowed here ...` |
| file `app.yaml` | `the file must be named riot-app.yaml` |
| Latin-1 byte in YAML | `'utf-8' codec can't decode byte 0xe9 ...` (no traceback) |
| YAML path is a directory / mode 000 | `[Errno 21] Is a directory` / `[Errno 13] Permission denied` |
| output dir read-only (555) | `riot-app.inc.mk: cannot write: [Errno 13] ...`; no temp file left |
| `riot-app.inc.mk` is a directory | `cannot read: [Errno 21] Is a directory` |
| 3 files, m1 `quiet: 017`, m3 no schema_version | both errors reported, `2 file(s) failed; nothing written`, m2 not written; `--check` reports both errors plus `m2/riot-app.inc.mk: missing` |
| valid new file | rc=0, mode 664 (umask 002), no leftovers, content = HW fragment |
| rewrite of a 640 file | rc=0, mode stays 640, `QUIET ?= 0` |

7. Negative tests of the first run, repeated (`$S/neg1.sh RIOT_Test`): all
   rc=1, nothing written, same messages as before (unknown key, `develhelp: 2`,
   `"1"`, list as board, `$(FOO)`, duplicate items, duplicate key line 25,
   `BOARD` in app_defaults (now short "not allowed here"), lowercase name,
   absolute dir, two bases, missing `riotbase`, YAML syntax error, top-level
   list, jsonschema not importable). Changed by design: missing
   `application` is now valid.
8. CI check and `--all` in `$S/newclone` (files restored with `cp -p` from
   RIOT_Test after each case; final `cmp` of the 4 files and check rc=0):

| Case | Result |
|---|---|
| A1 HW `quiet: on`, GN `ZEP_PORT_BASE: 017754`, `--all` | both errors, `2 file(s) failed; nothing written`, rc=1, fragments unchanged (md5) |
| A2 HW `quiet: 0` (valid), GN `0x10`, `--all` | GN error, `nothing written`, HW fragment not rewritten; CI check rc=1 reports GN error **and** `hello-world/riot-app.inc.mk: outdated`; `just generate-app-config` rc=1 |
| N1 `DEVELHELP ?= 0` in HW fragment | rc=1 outdated |
| N2 extra `USEMODULE += xtimer` GN | rc=1 outdated |
| N3 extra blank line GN | rc=1 outdated |
| N4 HW fragment removed | CI rc=1 `missing`; `make -C <app> ...` from elsewhere, `make -f <abs>/Makefile RIOTBASE=...` from elsewhere and `make` in the app dir: rc=2, `Makefile:6: *** <tree>/examples/basic/hello-world/riot-app.inc.mk missing: run 'just generate-app-config' in the RIOT root.  Stop.`; `just generate-app-config` recreates it byte-identical (mode 664) |
| N5 HW yaml `quiet: 0`, not regenerated | rc=1 outdated |
| N6 HW yaml `quiet: loud` | rc=1 schema error |
| N7 HW yaml `schema_version: 2` | rc=1 version error |

9. CI scripts (no docker), in `$S/newclone`:
   `STATIC_TESTS="riot_app_config features" ./dist/tools/ci/static_tests.sh`
   → both checks ✓, rc=0. Path-based selection
   (`. dist/tools/ci/test_selection.sh; BASE_BRANCH=8a39e8ebb9; should_run <n>`;
   `git diff <base> -- <paths>` compares with the working tree incl.
   intent-to-add files): `riot_app_config`, `any_make_files`,
   `any_build_files`, `any_python_files`, `any_shell_files` → run;
   `features`, `any_c_files`, `board_doc` → skip. Matches: `riot_app_config`
   = the 4 tool/CI files + 4 YAML/fragments; `any_make_files` = 2 Makefiles +
   2 fragments; `any_build_files` = those + 2 YAMLs (the YAMLs only via
   `*riot-app.yaml`).
10. Sanity check pathspecs (`ENABLE_DOCKER_PINNING_TEST=0`), new script vs
    the script of `8a39e8ebb9` (`git show 8a39e8ebb9:dist/tools/buildsystem_sanity_check/check.sh > $S/oldsc/check.sh`,
    run with `RIOTBASE=<tree>`):

| Tree | new script | old script | outputs |
|---|---|---|---|
| RIOT_Test | rc=0, empty | rc=0, empty | identical |
| `$S/newclone` (P4 files intent-to-add) | rc=0, empty | rc=0, empty | identical |

    Positive control in `$S/newclone` (temporary): HW fragment + `BOARD = native`,
    `BOARD_INSUFFICIENT_MEMORY := foo`, `CFLAGS += -DDEVELHELP`; new file
    `tests/zz_p4probe/riot-app.inc.mk` with `APPLICATION = foo` (`git add -N`)
    → rc=1 with all four messages pointing at the `riot-app.inc.mk` lines.
    After removing the probe and restoring the fragment: rc=0.
11. Repository checks:

| Command | Where | Result |
|---|---|---|
| `just --fmt --check --unstable` | RIOT_Test, `$S/newclone` | rc=0 |
| `git diff --check` (whole tree) | RIOT_Test | rc=0 (the earlier blank line at EOF of `decision-log.md` is gone, the file now ends with the Nachtrag text) |
| `git diff --check` | `$S/newclone` (P4 files incl. new ones) | rc=0 |
| `python3 -m py_compile riot_app_config.py` | RIOT_Test | rc=0; `__pycache__` removed afterwards |
| `bash -n` on `static_tests.sh`, `test_selection.sh`, `check.sh` | RIOT_Test | ok |
| `dist/tools/ci/check_features_existing_inc_mk_is_up_to_date.sh` | RIOT_Test | rc=0 |
| `dist/tools/ci/check_riot_app_config_up_to_date.sh` | RIOT_Test, `$S/newclone` | rc=0 |
| line length ≤ 119 (`awk`) | `riot_app_config.py` | ok |
| flake8 / pylint / shellcheck | — | not installed, not run |

### Result

Gate P4 still met (all baseline files byte-identical for HW/native64,
HW/native, GN/native64; 25 precedence cases identical); `make -f <abs>/Makefile`
from another directory now finds the fragment; the missing fragment, YAML 1.1
number/boolean forms, wrong `schema_version`, unreadable/undecodable files and
invalid files under `--all` all fail with clear messages and without writing.
The CI check is wired into `static_tests.sh`. Nothing committed.

Remaining limits: `riotbase` stays `$(CURDIR)`-relative (`make -f` from
elsewhere needs `RIOTBASE`, as upstream); the `riot/static-test-tools` image
must get jsonschema before upstreaming; conditionals stay in the Makefile;
dependency resolution stays in Make until P6; only two apps migrated.

## Real build after the review fixes (main session, 2026-11-13)

`hello-world`, `BOARD=native64`, `make all` with `BINDIRBASE` in a scratch
directory, in two clones of `8a39e8ebb9` at paths of equal length: `ref`
(unchanged) and `cur` (with the current `Makefile`, `riot-app.yaml`,
`riot-app.inc.mk`). Both rc 0; `nm | sort` byte-identical including addresses
(275 lines); `size` identical (text 29078, data 1080, bss 59128). A first
comparison against a build inside `RIOT_Test` differed only in addresses
(text +32 bytes) because the checkout path is embedded in strings (assert
file names, `DEVELHELP=1`); symbol names and types were identical.
