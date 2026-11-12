# Migrationsumfang — 71 Kandidaten (aus `riot_all_make_targets.xlsx`, Sheet „Migration Candidates“)

> **Hinweis 2026-11-12 (D17):** Die Dispositionen `MIGRATE`/`BRIDGE` und die
> Wellen 2/3 unten beschreiben das Workbook. Für die just-Schicht gilt nur
> noch Gruppe 1 ohne jeden `make`-Aufruf; maßgeblich ist `just-scope.md`.

Grundlage: RIOT master `0be9299ca9`, Erhebung 2026-11-09. Ein Target-Name = eine Zeile.
Die Tabelle ist aus dem Workbook generiert; bei Abweichungen gilt das Workbook.

| Welle | Umfang | Disposition | Anzahl |
|---|---|---|---:|
| 1 | MIGRATE, Gruppe 1 — direkt als just-Rezeptur | MIGRATE | 29 |
| 2 | MIGRATE, Gruppen 2A/2B/2C — just setzt Kontext und ruft bestehende Logik | MIGRATE | 15 |
| 3 | BRIDGE — just delegiert an make (BOARD/CPU/Modul-/Feature-Auflösung) | BRIDGE | 27 |
| **Gesamt** | | | **71** |

## Welle 1 — reine just-Rezeptur (29)

| Target | Gruppe | Scope | Aktion | Quelle / Evidenz | Weitere Deklarationsstellen |
|---|---|---|---|---|---|
| `build` | 1 | Doc | Build the Starlight documentation site | doc/starlight/Makefile:12 (new in complete inventory) | — |
| `check` | 1 | Doc | Run Doxygen checks | doc/doxygen/Makefile:94 (new in complete inventory) | — |
| `code_of_conduct` | 1 | Doc | Integrate CODE_OF_CONDUCT.md | doc/starlight/Makefile:33 (new in complete inventory) | — |
| `coding_conventions` | 1 | Doc | Integrate CODING_CONVENTIONS.md | doc/starlight/Makefile:49 (new in complete inventory) | — |
| `coding_conventions_cpp` | 1 | Doc | Integrate CODING_CONVENTIONS_C++.md | doc/starlight/Makefile:54 (new in complete inventory) | — |
| `contributing` | 1 | Doc | Integrate CONTRIBUTING.md | doc/starlight/Makefile:71 (new in complete inventory) | — |
| `dev` | 1 | Doc | Run the Starlight dev server | doc/starlight/Makefile:21 (new in complete inventory) | — |
| `doc` | 1 | App / help | Generate documentation | Makefile:9-14 | — |
| `doc-ci` | 1 | Root | Generate CI documentation | Makefile:9-13 | — |
| `doc-latex` | 1 | App / help | Generate LaTeX documentation | Makefile:9-14 | — |
| `doc-man` | 1 | App / help | Generate man documentation | Makefile:9-14 | — |
| `doc-starlight` | 1 | Root | Build Starlight documentation site | Makefile:15-16 | — |
| `doxygen-version` | 1 | Doc | Print the Doxygen version | doc/doxygen/Makefile:62 (new in complete inventory) | — |
| `governance` | 1 | Doc | Integrate GOVERNANCE.md | doc/starlight/Makefile:39 (new in complete inventory) | — |
| `graphviz-check` | 1 | Doc | Check Graphviz availability | doc/doxygen/Makefile:74 (new in complete inventory) | — |
| `html` | 1 | Doc | Build the HTML documentation | doc/doxygen/Makefile:88 (new in complete inventory) | — |
| `info-applications` | 1 | Root | List application directories | makefiles/app_dirs.inc.mk:26-27 | — |
| `info-boards` | 1 | App / help | List boards | makefiles/boards.inc.mk:20 | — |
| `info-emulated-boards` | 1 | App / help | List emulated boards | makefiles/boards.inc.mk:32 | — |
| `integrate_outside_files` | 1 | Doc | Copy repository markdown files into the doc site | doc/starlight/Makefile:30 (new in complete inventory) | — |
| `latex` | 1 | Doc | Build the LaTeX documentation | doc/doxygen/Makefile:114 (new in complete inventory) | — |
| `list-ttys` | 1 | App / help | List serial devices | Makefile.include:823 | — |
| `lostandfound` | 1 | Doc | Integrate LOSTANDFOUND.md | doc/starlight/Makefile:44 (new in complete inventory) | — |
| `man` | 1 | Doc | Build the man pages | doc/doxygen/Makefile:98 (new in complete inventory) | — |
| `preview` | 1 | Doc | Preview the Starlight documentation site | doc/starlight/Makefile:17 (new in complete inventory) | — |
| `print-versions` | 1 | Root | Print host toolchain versions | Makefile:26-27 | — |
| `security` | 1 | Doc | Integrate SECURITY.md | doc/starlight/Makefile:59 (new in complete inventory) | — |
| `unittests` | 1 | Doc | Integrate the unit-test README | doc/starlight/Makefile:65 (new in complete inventory) | — |
| `welcome` | 1 | Root | Print root-directory usage help | Makefile:81 | — |

## Welle 2 — just mit Make-Kontext (15)

| Target | Gruppe | Scope | Aktion | Quelle / Evidenz | Weitere Deklarationsstellen |
|---|---|---|---|---|---|
| `check-toolchain-supported` | 2A | App / help | Validate selected toolchain | makefiles/info.inc.mk:263-264 | — |
| `help` | 2A | App / help | List app target interface | Makefile.include:1000-1001 | Makefile.include:1000; dist/tools/zep_dispatch/Makefile:51 |
| `reset` | 2A | App / help | Reset target hardware | Makefile.include:874 | — |
| `usb_id_check` | 2A | App / help | Validate USB identifiers | makefiles/usb-codes.inc.mk:21 | — |
| `cleanterm` | 2B | App / help | Open unwrapped terminal | Makefile.include:818 | Makefile.include:818; Makefile.include:819 |
| `debug-client` | 2B | App / help | Start debug client | Makefile.include:843-851 | Makefile.include:843; Makefile.include:850 |
| `debug-server` | 2B | App / help | Start debug server | Makefile.include:856-864 | Makefile.include:856; Makefile.include:863 |
| `clean` | 2C | App / help | Remove build products | Makefile:45-47; Makefile.include:750 | Makefile.include:750; Makefile.base:28; Makefile:45; makefiles/tools/bossa-build.inc.mk:13; dist/tools/doxygen/Makefile:108; dist/tools/edbg/Makefile:24; dist/tools/mspdebug/Makefile:24; dist/tools/sliptty/Makefile:12; (+36 weitere) |
| `clean-intermediates` | 2C | App / help | Remove intermediate objects | Makefile.include:760 | — |
| `clean-pkg` | 2C | App / help | Remove package products | Makefile.include:766 | — |
| `distclean` | 2C | App / help | Remove all products | Makefile:48-56; Makefile.include:769 | Makefile.include:769; Makefile:48; dist/tools/doxygen/Makefile:105; dist/tools/sliptty/Makefile:15; dist/tools/ethos/Makefile:9; dist/tools/uhcpd/Makefile:19; dist/tools/riotboot_gen_hdr/Makefile:43; dist/tools/riotboot_serial/Makefile:16; (+15 weitere) |
| `docclean` | 2C | Root | Delete documentation build output | Makefile:18-20 | — |
| `install` | 2C | Tool | Install the host tool under $(prefix)/bin | dist/tools/lpc2k_pgm/Makefile:47-48 | dist/tools/lpc2k_pgm/Makefile:47; dist/tools/tunslip/Makefile:6; doc/starlight/Makefile:6 |
| `pkg-clean` | 2C | Root | Delete all package build output | Makefile:22-24 | — |
| `generate-Makefile.ci` | 3 | App / help | Generate CI board exclusions | makefiles/info-global.inc.mk:149-150; dist/tools/insufficient_memory/create_makefile.ci.sh:55 | — |

## Welle 3 — just→make-Bridge (27)

| Target | Gruppe | Scope | Aktion | Quelle / Evidenz | Weitere Deklarationsstellen |
|---|---|---|---|---|---|
| `check-kconfig-errors` | 2A | Root | Validate Kconfig configuration | makefiles/kconfig.mk:250 | — |
| `info-applications-supported-boards` | 2A | Root | List supported boards per application | makefiles/app_dirs.inc.mk:30-33 | makefiles/app_dirs.inc.mk:30; makefiles/app_dirs.inc.mk:35 |
| `info-boards-collect` | 2A | Root | Record supported-board metadata | makefiles/info-global.inc.mk:158 | — |
| `info-boards-features-blacklisted` | 2A | Root | List boards with blacklisted features | makefiles/info-global.inc.mk:143 | — |
| `info-boards-features-conflicting` | 2A | Root | List boards with conflicting features | makefiles/info-global.inc.mk:146 | — |
| `info-boards-features-missing` | 2A | Root | List boards with missing features | makefiles/info-global.inc.mk:140 | — |
| `info-boards-supported` | 2A | App / help | List supported boards | makefiles/info-global.inc.mk:137 | makefiles/info-global.inc.mk:137; makefiles/tests/feature_resolution/Makefile:7; tests/build_system/board_alias/Makefile:7 |
| `info-build` | 2A | App / help | Print resolved build information | makefiles/info.inc.mk:33 | — |
| `info-build-json` | 2A | App / help | Print resolved build JSON | makefiles/info.inc.mk:165 | — |
| `info-cpu` | 2A | App / help | Print resolved CPU | makefiles/info.inc.mk:237 | — |
| `info-features-missing` | 2A | App / help | List missing features | makefiles/info.inc.mk:246 | — |
| `info-features-provided` | 2A | App / help | List provided features | makefiles/info.inc.mk:240 | — |
| `info-features-required` | 2A | App / help | List required features | makefiles/info.inc.mk:243 | — |
| `info-features-used` | 2A | App / help | List used features | makefiles/info.inc.mk:249 | — |
| `info-files` | 2A | App / help | List participating files | makefiles/info.inc.mk:213 | makefiles/info.inc.mk:213; makefiles/info.inc.mk:214 |
| `info-iotlab-node` | 2A | Root | Print the resolved IoT-LAB node | dist/testbed-support/makefile.iotlab.single.inc.mk:175 | — |
| `info-kconfig-variables` | 2A | App / help | List CONFIG variables | makefiles/info.inc.mk:254 | — |
| `info-modules` | 2A | App / help | List resolved modules | makefiles/info.inc.mk:231 | — |
| `info-packages` | 2A | App / help | List resolved packages | makefiles/info.inc.mk:234 | — |
| `info-programmers-supported` | 2A | App / help | List supported programmers | makefiles/info.inc.mk:266 | — |
| `info-rust` | 2A | App / help | Print Rust integration details | makefiles/info.inc.mk:269 | — |
| `info-stm32` | 2A | Root | Print resolved STM32 CPU/memory information | cpu/stm32/Makefile.include:53-58 | — |
| `info-toolchains-supported` | 2A | App / help | List supported toolchains | makefiles/info.inc.mk:260 | — |
| `info-unittests` | 2A | Root | List selected unit-test suites | tests/unittests/Makefile:86-87 | — |
| `info-buildsize` | 2B | App / help | Report firmware size | makefiles/info.inc.mk:30 | — |
| `info-buildsizes-diff` | 2B | Root | Compare firmware sizes across two build trees | makefiles/info-global.inc.mk:77-115 | makefiles/info-global.inc.mk:77; makefiles/info-global.inc.mk:78 |
| `info-objsize` | 2B | App / help | Report object sizes | makefiles/info.inc.mk:12 | — |
