Application configuration in YAML (`riot-app.yaml`)
===================================================

An application can keep its settings in a `riot-app.yaml` file next to its
`Makefile`. This file is the authoritative source of the settings; it holds
no Make syntax, so that tools other than Make can read it.

`riot_app_config.py` checks each `riot-app.yaml` against
`riot-app.schema.json` (JSON Schema, draft 2020-12) and generates
`riot-app.inc.mk` next to it. The generated file is checked in and included
by the application `Makefile`. It is a transitional adapter for Make: do not
edit it by hand.

Usage
-----

After changing a `riot-app.yaml`, run in the root of the RIOT repository:

    just generate-app-config

which runs `dist/tools/riot_app_config/riot_app_config.py --all`. Make does
not read `riot-app.yaml`: until you regenerate, `make` builds with the old
settings of `riot-app.inc.mk`. CI catches a forgotten regeneration.

Single files (named `riot-app.yaml`) can be given instead of `--all`. All
given files are checked first and every error is reported; if any file is
invalid, nothing is written. Fragments are replaced atomically. With
`--check` the script writes nothing and fails if a `riot-app.inc.mk` is
missing or outdated. CI runs it through
`dist/tools/ci/check_riot_app_config_up_to_date.sh`, which
`dist/tools/ci/static_tests.sh` calls when a `riot-app.yaml`, a
`riot-app.inc.mk` or this tool changes (test name `riot_app_config`).

If `riot-app.inc.mk` is missing, the application `Makefile` stops with
`... riot-app.inc.mk missing: run 'just generate-app-config' in the RIOT root`.

Requirements: Python 3, PyYAML and jsonschema (Debian/Ubuntu:
`python3-yaml`, `python3-jsonschema`). Without jsonschema the script stops
with an error; it never writes an unchecked file. The CI images that run
the static tests (`riot/static-test-tools`) must provide jsonschema.

Values
------

Every file starts with `schema_version: 1`; other versions are rejected.
The version is not written to `riot-app.inc.mk`.

YAML 1.1 (PyYAML) turns some plain values silently into numbers or
booleans. The script does not accept that: only plain decimal integers
(`0`, `17754`, `-3`) are numbers. Values such as `017754` (octal), `0x10`,
`0b11`, `1:30` (sexagesimal), `1_000`, `1.0`, `.inf` and the booleans
`yes`/`no`/`on`/`off`/`true`/`false` are errors; quote them if text is
meant.

Keys
----

Each key sets one Make variable with the operator that application Makefiles
use, so the environment and the command line still override the values:

| Key                     | Make                                     |
|-------------------------|------------------------------------------|
| `schema_version`        | (required, `1`; not written)             |
| `application`           | `APPLICATION = <value>` (optional)       |
| `board`                 | `BOARD ?= <value>`                       |
| `riotbase`              | `RIOTBASE ?= $(CURDIR)/<value>`          |
| `usemodule`             | `USEMODULE += <item>` (one line each)    |
| `usepkg`                | `USEPKG += <item>`                       |
| `disable_module`        | `DISABLE_MODULE += <item>`               |
| `features_required`     | `FEATURES_REQUIRED += <item>`            |
| `features_required_any` | `FEATURES_REQUIRED_ANY += <a\|b>`        |
| `features_optional`     | `FEATURES_OPTIONAL += <item>`            |
| `features_blacklist`    | `FEATURES_BLACKLIST += <item>`           |
| `cflags`                | `CFLAGS += <flag>`                       |
| `develhelp`             | `DEVELHELP ?= 0\|1`                      |
| `quiet`                 | `QUIET ?= 0\|1`                          |
| `werror`                | `WERROR ?= 0\|1`                         |
| `app_defaults`          | `<NAME> ?= <value>` (sorted by name)     |
| `external_board_dirs`   | `EXTERNAL_BOARD_DIRS += <base>/<path>`   |
| `external_module_dirs`  | `EXTERNAL_MODULE_DIRS += <base>/<path>`  |
| `external_pkg_dirs`     | `EXTERNAL_PKG_DIRS += <base>/<path>`     |

`app_defaults` holds variables that only the application reads (for example
`USE_ZEP`); names of the other keys' variables and RIOT build variables
(`CPU`, `CPU_MODEL`, `CFLAGS`, `CXXFLAGS`, `LINKFLAGS`, `LDFLAGS`,
`DEFAULT_MODULE`, `BOARD_INSUFFICIENT_MEMORY`, `FEATURES_PROVIDED`, ...; full
list in the schema) are not allowed there. `cflags` must not contain
`-DDEVELHELP`; use `develhelp`. Entries of the `external_*_dirs` lists name
their base: `riotbase: <path>` or `appdir: <path>`. Unknown keys, wrong
types, duplicate keys or list items, and `$`, `#`, `\` or white space in
values are errors. Test applications leave out `application` (the sanity
check forbids `APPLICATION` in tests).

What stays in the Makefile
--------------------------

Settings that depend on a condition (e.g. `ifeq (1,$(USE_ZEP))`) and
includes after `$(RIOTBASE)/Makefile.include` stay in the application
`Makefile`. Include the fragment where the settings used to be, before such
conditions:

```make
RIOT_APP_CONFIG_MK := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/riot-app.inc.mk
ifeq (,$(wildcard $(RIOT_APP_CONFIG_MK)))
  $(error $(RIOT_APP_CONFIG_MK) missing: run 'just generate-app-config' in the RIOT root)
endif
include $(RIOT_APP_CONFIG_MK)

include $(RIOTBASE)/Makefile.include
```

The path is taken from the Makefile itself (before any other include), so
`make -C <app>`, `make` in the application directory and
`make -f <app>/Makefile` find the fragment. As before, `riotbase` is
relative to the current directory (`$(CURDIR)`): with `make -f` from another
directory, give `RIOTBASE` as well.

Module dependencies are still resolved by Make.
