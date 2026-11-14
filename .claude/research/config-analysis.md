# Konfigurationsanalyse — Roadmap P4, Schritt 1

Stand 2026-11-13 · Agent `config-analyst` · Referenz: RIOT master
`0be9299ca97e5db753861f326106619ca7c72c4a` (`/home/mohammadjavad/Documents/RIOT`,
nur gelesen) · GNU Make 4.3 · just 1.59.0 · gcc 13.3.0 · Linux x86_64,
`getconf LONG_BIT` = 64.

Umfang: nur Analyse (P4/1). Kein Makefile, kein justfile, kein Code geändert.
Geschrieben wurden nur diese Datei und `p4-baseline/`. Nichts committet.

Apps und Boards (Regel 7):

| Kürzel | App-Pfad (geprüft, existiert) | Boards |
|---|---|---|
| HW | `examples/basic/hello-world` | `native64`, `native` |
| GN | `examples/networking/gnrc/networking` (Pfad aus dem Auftrag stimmt) | `native64` |

Kennzeichnung: **[obs]** = [observation], beobachtet (Befehl + Commit + `file:line`),
**[inf]** = [inference], Schlussfolgerung. Alle `file:line` beziehen sich auf `0be9299ca9`.

## 0. Wie gemessen wurde (Schreibfreiheit)

- Zuerst in einem `git clone --shared` im Scratch-Verzeichnis geprüft, ob
  `info-build-json` und `info-debug-variable-*` Dateien schreiben:
  `git status --short --ignored` vorher/nachher identisch. Danach im
  Referenz-Checkout ausgeführt, wieder vorher/nachher identisch (die dort schon
  vorhandenen ignorierten Dateien, z. B. `examples/basic/hello-world/bin/`,
  stammen nicht aus diesem Lauf und blieben unverändert). **[obs]**
- Herkunft der letzten Zuweisung je Variable: `make --no-print-directory -pRrq
  -C <app> BOARD=native64 info-debug-variable-BOARD` (Klon), Ausgabe-Zeilen
  `# makefile (from '<datei>', line N)`. **[obs]**
- Alle Zuweisungsstellen: `grep -nE '^\s*(export\s+|override\s+)?VAR\s*(\?|:|\+|::)?='`
  über genau die Dateien in `MAKEFILE_LIST` von GN (96 eindeutige Dateien;
  HW liest eine echte Teilmenge davon, GN zusätzlich `Makefile.ci`,
  `sys/net/gnrc/Makefile.dep`, `sys/ztimer/…`, `sys/xtimer/…`,
  `makefiles/default-radio-settings.inc.mk` u. a.). **[obs]**

## 1. Auswertungsreihenfolge der Makefiles (App-Build)

Befehl: `make --no-print-directory -C <app> BOARD=native64 info-debug-variable-MAKEFILE_LIST`
(HW: 120 Einträge, GN: mehr; Reihenfolge = Lesereihenfolge). **[obs]**

| # | Datei (Einstieg `file:line`) | Inhalt für die Konfiguration |
|---|---|---|
| 0 | Kommandozeile, dann Umgebung | `make VAR=x` schlägt jede normale Zuweisung; Umgebung nur `?=`-Defaults (siehe 2.3) |
| 1 | App-`Makefile` (HW:2–16, GN:2–67) | `APPLICATION =`, `BOARD ?=`, `RIOTBASE ?=`, `USEMODULE +=`, `DEVELHELP ?=`, `QUIET ?=`, `EXTERNAL_BOARD_DIRS +=`; GN mit Bedingung `ifeq (1,$(USE_ZEP))` (GN:50–52) |
| 2 | `Makefile.include:47` `include $(RIOT_MAKEFILES_GLOBAL_PRE)` | nutzerweite Vor-Konfiguration (leer, wenn nicht gesetzt) |
| 3 | `Makefile.include:53` `-include Makefile.local` | lokale App-Overrides (in HW/GN nicht vorhanden) |
| 4 | `Makefile.include:56–70` | `?=`-Defaults der Verzeichnisse (`RIOTBASE`, `RIOTCPU`, `RIOTBOARD`, `EXTERNAL_*_DIRS`, `BINDIRBASE` …) |
| 5 | `Makefile.include:75` → `makefiles/board_alias.inc.mk` | `native` → `native$(getconf LONG_BIT)` per `override BOARD :=` (`board_alias.inc.mk:8,21`) |
| 6 | `Makefile.include:77` `BINDIR ?= $(BINDIRBASE)/$(BOARD)`, `:80` `-include Makefile.ci` | `BINDIR` erst nach Alias-Auflösung; GN liest `Makefile.ci` (nur `BOARD_INSUFFICIENT_MEMORY`) |
| 7 | `Makefile.include:106` → `makefiles/setup_dirs.inc.mk:28–42` | `override …:= $(abspath …)` für alle Pfadvariablen |
| 8 | `Makefile.include:120–208` | utils, docker, `boards.inc.mk`, TOOLCHAIN-Default (`:160–171`), `BOARDDIR`-Suche (`:196–203`), `info.inc.mk` (`:205`), `QUIET ?= 1` (`:218`), `DEVELHELP ?= 0` (`:241`), `WERROR ?= 1` (`:261`), `BOARD :=`/`APPLICATION := $(strip …)` (`:274–275`) |
| 9 | `Makefile.include:333` → `Makefile.features` → `$(BOARDDIR)/Makefile.features` (setzt `CPU`), `$(RIOTCPU)/$(CPU)/Makefile.features` | `FEATURES_PROVIDED`, `CPU`, `NATIVE_ARCH_BIT` |
| 10 | `Makefile.include:342–343` `pseudomodules.inc.mk`, `defaultmodules_regular.inc.mk` | `DEFAULT_MODULE +=` Grundmenge |
| 11 | `Makefile.include:346` `makefiles/kconfig.mk` | Kconfig nur aktiv, wenn `SHOULD_RUN_KCONFIG` (siehe 3.3) |
| 12 | `Makefile.include:349` `features_check.inc.mk`, `:352` `USEMODULE += $(filter-out $(DISABLE_MODULE),$(DEFAULT_MODULE))`, `:355` `USEMODULE := $(sort …)` | erste Feature-Prüfung, Default-Module einmischen |
| 13 | `Makefile.include:358` → `makefiles/dependency_resolution.inc.mk` (rekursiv, `:40` include sich selbst) | je Durchlauf: `PKG_PATHS` (`:11`), `Makefile.dep` (`:18`, dieses liest App-`Makefile.board.dep`, Board-, CPU-, `sys/`-, `drivers/`-, Modul- und Paket-`Makefile.dep`), `boards/Makefile.features` (`:22`), `features_check.inc.mk` (`:25`), `features_modules.inc.mk` (`:28`); Abbruch, wenn `USEMODULE USEPKG FEATURES_USED` stabil (`:36–40`). Durchläufe: **HW 3, GN 4** (Anzahl `dependency_resolution.inc.mk` in `MAKEFILE_LIST`). Im letzten Durchlauf: `defaultmodules_no_recursive_deps.inc.mk`, `defaultmodules_deps.inc.mk`, `deprecated_modules.inc.mk`, `features_existing.inc.mk` (`:42–76`) |
| 14 | `Makefile.include:371–374` Board-/CPU-`Makefile.include`, dann `:377–409` Programmer, serial, Emulator, Toolchain | Werkzeugvariablen (`TERMPROG`, `DEBUGGER`, `CC` …), CPU-/Arch-`CFLAGS` (`makefiles/arch/native.inc.mk`) |
| 15 | `Makefile.include:425–535` `ubsan`, `cflags.inc.mk` (`:477`), `VERSION`, `git_version`, `sys/Makefile.include` (`:507`), Treiber-/Paket-/externe Modul-`Makefile.include` (`:510–516`), `bindist`, `modules.inc.mk` (`:535`) | Rest der `CFLAGS`/`INCLUDES` aus aufgelösten Modulen |
| 16 | `Makefile.include:582–1075` riotboot, programmer, tests, `vars.inc.mk` (`:899`, 90 `export`-Zeilen), … `$(RIOT_MAKEFILES_GLOBAL_POST)` (`:1075`) | Exporte an Sub-Makes |
| 17 | App-`Makefile` **nach** dem Include (nur GN:72) `include $(RIOTMAKE)/default-radio-settings.inc.mk` | App-Konfiguration nach der Auflösung (`DEFAULT_CHANNEL`, `DEFAULT_PAN_ID` → `CFLAGS`) |

[inf] Kernaussage: Eingaben (Schritte 0–3, 17) und Auflösung (9–15) sind in
einem einzigen Make-Lauf verschränkt; Board-Alias, Defaults und Abhängigkeiten
überschreiben bzw. ergänzen Eingaben an mehreren Stellen. Eine zentrale Datei
kann nur die Schritte 0–3/17 ersetzen; Schritt 13 bleibt Make (Roadmap P4/3:
„Make bleibt Resolver“).

## 2. Konfigurationsvariablen

### 2.1 Tabelle

Spalten: Op. = Operator an der jeweiligen Stelle; Kl. = Klasse (E = Eingabe,
A = abgeleitet, W = Werkzeug); DR = braucht Abhängigkeitsauflösung
(`dependency_resolution.inc.mk`); Werte aus `p4-baseline/info-debug-variables.txt`
bzw. `*.info-build-json.json`. „HW64“ = HW/native64, „HWn“ = HW/native, „GN64“ = GN/native64.

| Variable | Definiert (file:line, alle Stellen im gelesenen Satz) | Op. | Kl. | DR | HW64 | HWn | GN64 |
|---|---|---|---|---|---|---|---|
| `BOARD` | HW `Makefile:5`, GN `Makefile:5`; `board_alias.inc.mk:21`; `Makefile.include:274`; export `vars.inc.mk` | `?=`; `override :=`; `:=` (strip); `export` | E | nein | `native64` (Kommandozeile) | `native64` (Eingabe `native`, Alias) | `native64` |
| `BOARD_ALIAS` | `board_alias.inc.mk:3,4,8` | `+=` (mit `$(shell getconf LONG_BIT)`, `:7`) | A (host-abhängig) | nein | `… native:native64` | gleich | gleich |
| `RIOTBASE` | HW `Makefile:8`, GN `Makefile:8`; `Makefile.include:56`; `setup_dirs.inc.mk:28`; export `vars.inc.mk` | `?=`; `?=`; `override :=` | E (Pfad) | nein | `/home/…/RIOT` | gleich | gleich |
| `APPLICATION` | HW `Makefile:2`, GN `Makefile:2`; `Makefile.include:275`; Pflichtprüfung `:123–125`; export | `=`; `:=` (strip) | E | nein | `hello-world` | `hello-world` | `gnrc_networking` |
| `DEVELHELP` | HW `Makefile:13`, GN `Makefile:42`; `Makefile.include:235` (wenn `VERBOSE_ASSERT=1`), `:241`; Wirkung `:242–244` (`CFLAGS += -DDEVELHELP`) | `?=`; `:=`; `?=` | E | nein | `1` | `1` | `1` |
| `QUIET` | HW `Makefile:16`, GN `Makefile:65`; `Makefile.include:218`; export `vars.inc.mk:6` | `?=`; `?=`; `export` | E (Ausgabe) | nein | `1` | `1` | `1` |
| `WERROR` | `Makefile.include:261`; Wirkung `:262–264` | `?=` | E | nein | `1` | `1` | `1` |
| `USEMODULE` (Eingabe) | GN `Makefile:12–31` (15 Zeilen), `:51` (bedingt); HW keine | `+=` | E | — | — (keine) | — | 15 Module |
| `USEMODULE` (aufgelöst) | 810 Zuweisungen in 25 Dateien des GN-Satzes, u. a. `Makefile.include:352,355`, `dependency_resolution.inc.mk:31,64`, `features_modules.inc.mk:10,69–92`, `defaultmodules_deps.inc.mk:6–34`, `Makefile.dep`, `sys/Makefile.dep`; letzte Zuweisung `dependency_resolution.inc.mk:64`; export `vars.inc.mk:27` | `+=`, `:=` | A | **ja** | 42 (davon 15 ohne Default-Module in JSON) | 42 / 15 | 164 / 127 |
| `USEPKG` | Apps: keine; 22 bedingte `+=` u. a. `Makefile.dep:43–105`, `sys/Makefile.dep:234,523,659`, `boards/common/native/Makefile.dep:12,24`, `makefiles/stdio.inc.mk:45,59`; `dependency_resolution.inc.mk:32`; export `vars.inc.mk:29` | `+=`, `:=` | E + A | ja | leer | leer | leer |
| `DEFAULT_MODULE` | 34 Zuweisungen in 11 Dateien, u. a. `defaultmodules_regular.inc.mk:6`, `features_modules.inc.mk:66`, `defaultmodules_no_recursive_deps.inc.mk:7–18`, Modul-`Makefile.dep`; letzte `dependency_resolution.inc.mk:65` | `+=`, `:=` | A (App kann `+=`) | ja | 27 | 27 | 38 (37 nach `DISABLE_MODULE`) |
| `DISABLE_MODULE` | Apps: keine; `dependency_resolution.inc.mk:49,53` (bedingt); `sys/xtimer/Makefile.dep:23`; export `vars.inc.mk:30` | `+=`, `export` | E + A | ja | leer | leer | `auto_init_xtimer` (8× roh, aus `sys/xtimer/Makefile.dep:23`) |
| `FEATURES_REQUIRED` | 55 Zuweisungen in 12 Dateien, u. a. `features_check.inc.mk:5–7`, Modul-`Makefile.dep`; letzte `features_modules.inc.mk:139` | `+=` | E + A | ja | `arch_64bit arch_native cpu_native periph_gpio periph_pm periph_uart` (roh mit Duplikaten) | gleich | + `periph_cpuid periph_hwrng periph_timer` |
| `FEATURES_REQUIRED_ANY` | 3 Zuweisungen in 2 Dateien | `+=` | E + A | ja | leer | leer | leer |
| `FEATURES_OPTIONAL` | 21 Zuweisungen in 6 Dateien, u. a. `Makefile.dep:109,114,118` | `+=` | E + A | ja | 17 eindeutige | gleich | + `periph_rtt periph_hwrng periph_timer_query_freqs periph_cpuid` |
| `FEATURES_BLACKLIST` | keine Zuweisung im gelesenen Satz; gelesen `features_check.inc.mk:25,93` | — | E | ja (Wirkung) | leer | leer | leer |
| `CFLAGS` (Zusätze) | Apps: keine aktiven (GN `Makefile:60–63` nur auskommentiert); 64 Zuweisungen in 15 Dateien, u. a. `Makefile.include:236,243,248,256,263,268,1047`, `makefiles/cflags.inc.mk:31ff`, `makefiles/arch/native.inc.mk:133`, `default-radio-settings.inc.mk` (GN, bedingt) | `+=` | E + A | teilweise (modulabhängige Zusätze) | 41 Werte (37 eindeutig) | gleich | 45 (40 eindeutig) |
| `EXTERNAL_BOARD_DIRS` | GN `Makefile:67`; `Makefile.include:60`; `setup_dirs.inc.mk:40`; export `vars.inc.mk` | `+=`; `?=`; `:=` | E | nein | leer | leer | `…/tests/build_system/external_board_dirs/esp-ci-boards` |
| `EXTERNAL_MODULE_DIRS` | `setup_dirs.inc.mk:41` | `:=` | E | nein | leer | leer | leer |
| `EXTERNAL_PKG_DIRS` | `Makefile.include:64`; `setup_dirs.inc.mk:42` | `?=`; `:=` | E | nein | leer | leer | leer |
| `Makefile.local` | `Makefile.include:53` | `-include` | E (Datei) | nein | nicht vorhanden | — | nicht vorhanden |
| `RIOT_MAKEFILES_GLOBAL_PRE/POST` | `Makefile.include:47,1075` | `include` | E (Datei) | nein | ungesetzt | — | ungesetzt |
| Kconfig `app.config`/`user.config` | `kconfig.mk:36,40,66–72`; Aktivierung `:94` | `=`, `+=`, `?=` | E (Datei) | ja (Kconfig.dep) | nicht vorhanden, `SHOULD_RUN_KCONFIG` leer | — | nicht vorhanden |
| `USE_ZEP`, `ZEP_PORT_BASE` | GN `Makefile:46,49`; `boards/common/native/Makefile.include:22` | `?=` | E (App-spezifisch) | nein | `ZEP_PORT_BASE=17754` (Board-Default) | gleich | `USE_ZEP=0`, `17754` (App) |
| `TOOLCHAIN` | `Makefile.include:163,167,170` | `override :=` | E | nein | `gnu` | `gnu` | `gnu` |
| `CPU` | `boards/native64/Makefile.features:1`; Pflichtprüfung `Makefile.features` (Sanity-Check); export `vars.inc.mk:15` | `=` | A | nein (Board) | `native` | `native` | `native` |
| `CPU_MODEL` | keine Zuweisung für native; nur `export` `vars.inc.mk:16` | `export` | A | nein | leer | leer | leer |
| `NATIVE_ARCH_BIT` | `boards/native64/Makefile.features:4` | `=` | A | nein | `64` | `64` | `64` |
| `BINDIR` | `Makefile.include:77`; `setup_dirs.inc.mk:37` | `?=`; `override :=` | A (überschreibbar) | nein | `…/hello-world/bin/native64` | **gleich** (Alias) | `…/networking/bin/native64` |
| `FEATURES_USED` | `features_check.inc.mk:73`; `dependency_resolution.inc.mk:33` | `:=` | A | **ja** | `arch_64bit arch_native cpu_native periph_gpio periph_pm periph_uart` | gleich | + `periph_cpuid periph_hwrng periph_timer periph_timer_query_freqs` |
| `FEATURES_PROVIDED` | Board-/CPU-`Makefile.features`, `Makefile.features` | `+=` | A | teilweise | 29 eindeutige | gleich | gleich |
| `PKG_PATHS` | `dependency_resolution.inc.mk:11` | `:=` | A | **ja** | leer | leer | leer |
| `TERMPROG`, `DEBUGGER`, `CC`, `OBJCOPY` | Board-/CPU-/Toolchain-`Makefile.include` (Schritt 14) | `?=`, `=` | W | nein | `…/hello-world.elf`, `gdb`, `gcc`, `/usr/bin/objcopy` | gleich | `…/gnrc_networking.elf`, `gdb`, `gcc` |

Befehle (je Variable und Kombination, 41 Variablen):
`make --no-print-directory -C <app> BOARD=<board> info-debug-variable-<VAR> 2>/dev/null`
(Ausgabe und vollständige Liste: `p4-baseline/info-debug-variables.txt`,
`p4-baseline/commands.txt`). **[obs]**

### 2.2 Beobachtungen, die das Design betreffen

1. **`native` ist kein eigener Zustand.** HW/native und HW/native64 liefern
   byte-identisches `info-build-json` (gleicher SHA-256 `a0db5d3d…`), auch
   `BINDIR` endet auf `native64`. Ursache `board_alias.inc.mk:7–8,21`
   (`getconf LONG_BIT`). Einziger Unterschied: stderr-Hinweis
   `using BOARD="native64" as "native" on a 64-bit system`. **[obs]**
   [inf] Die Eingabe `BOARD: native` ist host-abhängig; ein zentraler
   Eingabe-Datensatz bleibt dadurch portabel, der aufgelöste Zustand nicht.
2. **`CFLAGS` auf der Kommandozeile ersetzt alles.**
   `make BOARD=native64 CFLAGS=-DFOO info-debug-variable-CFLAGS` → nur
   `-DFOO`; dagegen `CFLAGS=-DFOO make …` (Umgebung) → 42 Werte, `-DFOO`
   zuerst. **[obs]** [inf] „CFLAGS-Zusätze“ sind in Make nur über Umgebung
   oder App-Makefile additiv; ein Generator muss `+=` erzeugen, nicht `=`.
3. **Umgebung schlägt App-`?=`:** `DEVELHELP=0 make …` → `0`;
   `BOARD=native make …` → `native64`. **[obs]**
4. **Bedingte App-Konfiguration:** GN `Makefile:50–52`
   (`ifeq (1,$(USE_ZEP)) USEMODULE += socket_zep`) und GN `Makefile:72`
   (Include *nach* `Makefile.include`). **[obs]** [inf] Ein rein deklaratives
   Format deckt GN nur ab, wenn es Bedingungen oder einen „Rest bleibt im
   Makefile“-Mechanismus kennt.
5. **`info-build-json` deckt nicht alle Eingaben ab:** es fehlen `DEVELHELP`,
   `QUIET`, `WERROR`, `CPU_MODEL`, `PKG_PATHS`, `FEATURES_OPTIONAL` (nur
   `_ONLY`/`_MISSING`), `TOOLCHAIN`, `USE_ZEP`. `DEVELHELP`/`WERROR` sind nur
   indirekt über `CFLAGS` (`-DDEVELHELP`, `-Werror`) sichtbar.
   `USEMODULE` in JSON = `USEMODULE` ohne `DEFAULT_MODULE`
   (`info.inc.mk:186`). **[obs]**
6. **Absolute Pfade im JSON** (`APPDIR`, `RIOTBASE`, `BINDIR`, `CFLAGS`
   `-fmacro-prefix-map=…`, `-include …/riotbuild.h`). **[obs]** Gegenprobe:
   dieselben drei Befehle in `RIOT_Test` (HEAD `8a39e8ebb9`, enthält
   `0be9299ca9` + just-Schicht) liefern nach Ersetzen
   `RIOT_Test`→`RIOT` byte-identische Ausgaben. **[obs]** [inf] Ein
   Konsistenzcheck braucht Pfadnormalisierung.

## 3. Präzedenzfälle in RIOT für zentrale/generierte Konfiguration

### 3.1 `features.yaml` → `makefiles/features_existing.inc.mk` **[obs]**

- Quelle `features.yaml` (YAML 1.2, Kopf: „source of truth“), Schema
  `dist/tools/features_yaml2mx/schema.cddl` (16 Zeilen CDDL).
- Generator `dist/tools/features_yaml2mx/features_yaml2mx.py` (Python,
  `import argparse`, `import yaml` = PyYAML, Zeile 9–10; Ausgaben
  `--output-makefile`, `--output-md`).
- Aufruf: Root-`Makefile:29–32` (`generate-features`) und `:9–12`
  (Doku). In `RIOT_Test` nach D18/D20 über `just generate-features`.
- Generat hat Warnkopf („auto-generated … do not edit“,
  `features_existing.inc.mk:1–3`) und ist **eingecheckt**; gelesen in
  `dependency_resolution.inc.mk:76`.
- CI-Prüfung `dist/tools/ci/check_features_existing_inc_mk_is_up_to_date.sh`
  (SHA-256 vorher/nachher, regeneriert *in place*), aufgerufen
  `dist/tools/ci/static_tests.sh:119`; Testauswahl
  `dist/tools/ci/test_selection.sh:26`.
- **CDDL wird nirgends maschinell geprüft** (`grep -rn cddl` über `*.sh`,
  `*.py`, `*.yml`, Makefiles: kein Treffer). Das Schema ist Dokumentation.

### 3.2 `info-build-json` **[obs]**

- Existiert: `makefiles/info.inc.mk:165–210`, eingeführt `aba91f144c`
  (2020-10-08). JSON-Helfer `json_string_or_null` (`:129`),
  `to_json_string_list` (`:143`). 43 Schlüssel.
- Repo-interne Nutzer: nur zsh-Completion
  (`dist/tools/zsh-completion/zsh-riot.zsh:175`) und Release-Notes.
- Erzeugt keinen Schreibzugriff (Abschnitt 0); braucht vollständige
  Abhängigkeitsauflösung → Gruppe 2A, **nicht** just (D17, Roadmap P4/4).

### 3.3 Kconfig **[obs]**

- Vorhanden: Root-`Kconfig`, `kconfigs/` (2 Dateien), `makefiles/kconfig.mk`
  (eingebunden `Makefile.include:346`), 19 `app.config` im Repo (z. B.
  `examples/networking/coap/*`, `examples/networking/misc/lwm2m`).
- Aktiv nur, wenn `SHOULD_RUN_KCONFIG` gesetzt ist: Default
  `$(wildcard $(APPDIR)/*.config) $(wildcard $(APPDIR)/Kconfig)`
  (`kconfig.mk:94`), sonst bei `menuconfig` oder vorhandenem `out.config`.
  Kommentar `kconfig.mk:89–93`: Modulkonfiguration per Kconfig ist
  standardmäßig aus.
- HW und GN: kein `*.config`, kein `Kconfig` → `SHOULD_RUN_KCONFIG` leer
  (`info-debug-variable-SHOULD_RUN_KCONFIG`). Kconfig wirkt nur auf
  `CONFIG_*`-Symbole (Header `autoconf.h`), **nicht** auf `USEMODULE`.
- Merge-Reihenfolge der Kconfig-Dateien (`kconfig.mk:66–72`): CPU → Board →
  `KCONFIG_ADD_CONFIG` → `app.config` → `user.config` → Umgebung
  `RIOT_CONFIG_*`. [inf] Das ist RIOTs einziges bestehendes Muster für eine
  geschichtete, dateibasierte App-Konfiguration.

## 4. Gemessene Baseline

Ordner: `/home/mohammadjavad/Documents/RIOT_Test/.claude/research/p4-baseline/`

| Datei | SHA-256 |
|---|---|
| `hello-world.native64.info-build-json.json` | `a0db5d3d7635624fec59401a63e3ef1622271e89d875e212d8446a264de8bfbb` |
| `hello-world.native.info-build-json.json` | `a0db5d3d7635624fec59401a63e3ef1622271e89d875e212d8446a264de8bfbb` |
| `gnrc_networking.native64.info-build-json.json` | `6817f9544f8461c1e4d72bbff010fcbc63466b3bc925b6830bc06d07269d9967` |
| `*.stderr.txt` (native64: leer; native: Alias-Hinweis) | siehe `SHA256SUMS` |
| `info-debug-variables.txt` (41 Variablen × 3) | siehe `SHA256SUMS` |
| `commands.txt` (Befehle, Versionen) | siehe `SHA256SUMS` |

Befehle (Arbeitsverzeichnis `/home/mohammadjavad/Documents/RIOT`, Commit
`0be9299ca9`, Umgebung ohne `BOARD`/`CFLAGS`/`DEVELHELP`/`QUIET`/`WERROR`):

```sh
make --no-print-directory -C examples/basic/hello-world BOARD=native64 info-build-json
make --no-print-directory -C examples/basic/hello-world BOARD=native info-build-json
make --no-print-directory -C examples/networking/gnrc/networking BOARD=native64 info-build-json
```

Versionen: GNU Make 4.3, just 1.59.0 (für die Baseline nicht benutzt), GNU
bash 5.2.21, gcc 13.3.0, Linux 7.0.0-43-generic x86_64, `getconf LONG_BIT` 64.
Alle drei Ausgaben sind gültiges JSON (`python3 json.load`). Prüfen:
`cd p4-baseline && sha256sum -c SHA256SUMS`.

[inf] Die Baseline ist maschinen- und pfadabhängig (absolute Pfade, `gcc`-
Erkennung, `LONG_BIT`). Für das P4-Gate zählt der Vergleich alt/neu auf
derselben Maschine, nicht der Hash über Maschinen hinweg.

## 5. Offene Designfragen für den Nutzer (nicht entschieden)

Jede Frage mit Optionen, Belegen, Vor-/Nachteilen. Keine Empfehlung.

### F1 — Dateiformat der Eingabe-Konfiguration

| Option | Beleg | Für | Gegen |
|---|---|---|---|
| a) YAML (wie `features.yaml`) | Präzedenz 3.1, Roadmap P4/2 | in RIOT schon genutzt, PyYAML in CI vorhanden, Kommentare möglich | YAML-Fallen (Typ-Raten `on`/`no`, Einrückung), Parser-Abhängigkeit für jeden Leser |
| b) TOML | — (kein Präzedenzfall in RIOT) | eindeutige Typen, Python ≥ 3.11 `tomllib` ohne Zusatzpaket | neu für RIOT; Listen von Tabellen umständlich |
| c) JSON | `info-build-json` | gleiches Format wie der aufgelöste Zustand, überall lesbar | keine Kommentare, schlecht von Hand zu pflegen |
| d) Make-Fragment mit festem Teilsprachumfang (nur `VAR = …`/`+=`) | `Makefile.local`, `RIOT_MAKEFILES_GLOBAL_PRE` | kein Generator nötig | nicht tool-unabhängig (Meeting 11-06), andere Tools müssten Make-Syntax parsen |

### F2 — Schemasprache

| Option | Beleg | Für | Gegen |
|---|---|---|---|
| a) CDDL (wie `features.yaml`) | `schema.cddl`; CI prüft es nicht (3.1) | RIOT-Präzedenz, kompakt, IETF-Standard (RFC 8610) | in RIOT nur Dokumentation; Validator (`cddl`-Gem/Rust) wäre neue CI-Abhängigkeit |
| b) JSON Schema | — | breite Werkzeugbasis (Python `jsonschema`, Editor-Unterstützung), passt auch auf `resolved-state.json` | neue Abhängigkeit in RIOT, ausführlicher |
| c) kein formales Schema, Prüfung im Generator-Code | `features_yaml2mx.py` prüft faktisch so | keine Zusatzwerkzeuge | Vertrag nur im Code lesbar, schwächer als Thesis-Nachweis |

### F3 — Umfang der Eingaben im ersten PoC

| Option | Für | Gegen |
|---|---|---|
| a) minimal: `APPLICATION`, `BOARD`(-Default), `RIOTBASE`, `DEVELHELP`, `QUIET`, `USEMODULE` | deckt HW vollständig und GN fast vollständig ab | GN-Reste (`EXTERNAL_BOARD_DIRS`, `USE_ZEP`-Bedingung, Radio-Include) bleiben im Makefile |
| b) a) + `USEPKG`, `DISABLE_MODULE`, `FEATURES_REQUIRED/OPTIONAL/BLACKLIST`, `CFLAGS`-Zusätze, `EXTERNAL_*_DIRS`, `WERROR` | alle Eingabeklassen aus Tabelle 2.1 einmal belegt | für HW/GN teils leer → nur Syntax-, kein Verhaltensnachweis |
| c) b) + bedingte Einträge (z. B. `when: USE_ZEP == 1`) | GN vollständig abbildbar (2.2/4) | Format wird zur Mini-Sprache, Abstand zu Make schrumpft |
| d) b) + App-eigene Variablen (`USE_ZEP`, `ZEP_PORT_BASE`) als freie Schlüssel | flexibel | Schema schwer zu schließen; Tippfehler fallen nicht auf |

Querfrage: Werkzeugvariablen (`TERMPROG`, `PROGRAMMER`, `FLASHER`) und
`QUIET` — gehören sie in die Build-Konfiguration oder in eine getrennte
Werkzeug-/Benutzerdatei (vgl. Kconfig `app.config` vs. `user.config`,
`kconfig.mk:36,40`)?

### F4 — Ort der Datei

| Option | Für | Gegen |
|---|---|---|
| a) je App (`<app>/app.yaml` o. ä.) | entspricht heutigem App-Makefile; `APPDIR`-relativ wie `app.config` | Name kollisionsgefährdet mit Kconfig `*.config`-Wildcard (`kconfig.mk:94`) — Endung beachten |
| b) je App + Board-Overlays (`<app>/boards/<board>.yaml`) | bildet `Makefile.board.dep`/`BOARD_INSUFFICIENT_MEMORY` ab | mehr Dateien; im PoC nur native/native64 (Regel 7) |
| c) zentral im Repo (eine Datei für alle Apps) | ein Ort | widerspricht App-Lokalität; große Merge-Konflikte |
| d) Schichten: Repo-Defaults + App + Benutzer (wie `GLOBAL_PRE` → App → `Makefile.local`) | bildet die heutige `?=`-Kaskade explizit ab | Vorrangregeln müssen spezifiziert und getestet werden |

### F5 — Wie Make die Datei liest

| Option | Beleg | Für | Gegen |
|---|---|---|---|
| a) Generator → eingechecktes `*.inc.mk` | 3.1 (`features_existing.inc.mk`), Roadmap P4/3 | bewährt, Make braucht kein Python beim Build | zwei Wahrheiten im Repo, braucht CI-Up-to-date-Check |
| b) Generator → `*.inc.mk` in `$(BINDIR)` zur Build-Zeit (Make-Regel, „remaking makefiles“) | Kconfig `-include $(KCONFIG_OUT_CONFIG)` (`kconfig.mk`) | keine eingecheckte Kopie | Python + PyYAML werden Build-Voraussetzung; Make-Restart; bei `info-*` Schreibzugriff |
| c) Make liest direkt über `$(shell …)` | — | keine generierte Datei | Python bei jedem Make-Aufruf, auch `info-*`; schwer zu debuggen |
| d) Einstiegspunkt: `Makefile.local`-Mechanismus (`Makefile.include:53`) vs. eigenes `-include` an fester Stelle | 1, Schritt 3 | `Makefile.local` existiert schon | `Makefile.local` ist heute für Nutzer gedacht; Kollision möglich |

### F6 — Wie App-Makefiles weiter funktionieren

| Option | Für | Gegen |
|---|---|---|
| a) App-Makefile bleibt, inkludiert das Generat vor `Makefile.include` | minimal-invasiv, Bedingungen (GN:50–52, :72) bleiben möglich | zwei Orte für App-Konfiguration während der Übergangszeit |
| b) App-Makefile wird zum Zweizeiler (`include … Makefile.include`), alles in der Datei | ein Ort | GN braucht F3 c) oder d) |
| c) beides erlaubt, Datei optional (Fallback auf heutiges Makefile) | inkrementelle Migration App für App | Doppelte Definition muss erkannt werden (z. B. Fehler, wenn beide `USEMODULE` setzen?) |

Querfrage: Vorrang Kommandozeile/Umgebung gegenüber Datei — soll die Datei
`?=` (Umgebung gewinnt, heutiges Verhalten 2.2/3) oder `=` erzeugen? Für
`CFLAGS`/`USEMODULE` `+=` (2.2/2)?

### F7 — Konsistenzcheck

| Option | Beleg | Für | Gegen |
|---|---|---|---|
| a) Regenerieren + Hash-Vergleich des Generats | `check_features_existing_inc_mk_is_up_to_date.sh` | einfach, RIOT-üblich | prüft nur Datei→Generat, nicht Verhalten; regeneriert in place |
| b) `info-build-json` alt vs. neu (normalisiert, Schlüssel sortiert) | Roadmap-Gate P4, Baseline 4 | prüft Verhalten (aufgelöster Zustand) | braucht volle Auflösung je App/Board → teuer in CI; Pfadnormalisierung (2.2/6); fehlende Schlüssel (2.2/5) |
| c) b) + `info-debug-variable-*` für Eingaben, die JSON nicht zeigt | 2.2/5 | deckt `DEVELHELP`/`QUIET`/`WERROR` direkt ab | mehr Make-Aufrufe |
| d) Schema-Validierung der Eingabedatei | F2 | fängt Tippfehler früh | prüft keine Gleichheit mit Make |
| e) Negativtest: manipulierte Datei muss Check scheitern lassen | Roadmap-Gate P4 | belegt Wirksamkeit | Auswahl der Manipulationen festlegen |

### F8 — Export des aufgelösten Zustands (Ausblick P4/4, nicht P4/1)

- Ist `info-build-json` (43 Schlüssel, 2.2/5) der Vertrag, oder braucht es
  einen erweiterten/versionierten Export (z. B. mit `schema_version`,
  `DEVELHELP`, `PKG_PATHS`, relativen Pfaden)?
- Konsument ist laut D17/Roadmap P4/4 das Build-Werkzeug aus P6, **nicht**
  just; just liest weder Eingabedatei-Auflösung noch `resolved-state.json`.
  Offen: Darf just die *Eingabe*-Datei (unaufgelöst) lesen, z. B. für
  Gruppe-1-Rezepte, oder bleibt auch das ausgeschlossen?

## 6. Grenzen dieser Analyse

- Nur native/native64 (Regel 7): `CPU_MODEL`, `PKG_PATHS`, `USEPKG`,
  `FEATURES_BLACKLIST`, `EXTERNAL_MODULE_DIRS` sind in allen drei Kombinationen
  leer → Klasse und Ort belegt, Verhalten nicht.
- Zuweisungszählungen (810/34/55/21/3/64) per Regex über den GN-Dateisatz;
  mehrzeilige oder über `$(eval …)` erzeugte Zuweisungen sind nicht erfasst.
- `make -pRrq` zeigt nur die *letzte* Zuweisung je Variable; „alle Stellen“
  stammen aus `grep`, nicht aus Make.
