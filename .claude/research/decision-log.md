# Entscheidungsprotokoll — Inventar, Klassifikation, Migrationsumfang

Datum: 2026-11-09
Baseline: RIOT master `0be9299ca9` (Arbeitskopie `RIOT_Test` identisch)
Quelle: `riot_all_make_targets.xlsx`, Sheet „Summary“ und „Verification“

## D1 — Was ist die Grundgesamtheit?

**Entscheidung:** Das vollständige Inventar umfasst **2.314 eindeutige
Target-Namen**. Es ist Referenzmaterial, nicht der Migrationsumfang.

**Begründung:** Der statische Scan über 4.926 `Makefile*`/`*.mk`-Dateien,
die Root- und App-Make-Datenbank (`make -pRrq :`) und der Mehrkontext-Scan
liefern zusammen 2.314 Namen. Davon sind 1.991 keine stabil benennbaren
Ziele: 1.490 `CLEAN--`/`DISTCLEAN--`-Wrapper, 247 Datei-/Pfadziele,
165 variablen-expandierte Ziele, 50 Pattern-Regeln, 20 Modul-Regeln,
19 Spezial-/ interne Ziele.

**Konsequenz:** Die 2.314 werden im Workbook dokumentiert und bei Bedarf
gegen den Quellbaum geprüft, aber nie als Todo-Liste behandelt.

## D2 — Was ist die Arbeitsgrundlage?

**Entscheidung:** **323 benannte Targets** sind das Klassifikationsuniversum
und die Arbeitsgrundlage.

**Begründung:** Nur benannte Targets haben ein stabiles Interface und ein
eigenes Rezept. Die 87er-`help`-Liste ist kontextabhängig und deckt nur eine
App-/Board-Sicht ab (`native64: 87`, `iotlab-m3: 77`, `xipfs/native64: 82`).
Sie ist eine Teilmenge, nicht das Universum: `87 + 215 + 21 = 323`.

**Konsequenz:** Jede Klassifikations- und Migrationsaussage bezieht sich auf
die 323. Die 87 bleiben als kanonischer Regressionsvergleich erhalten.

## D3 — Was wird migriert? — **für die just-Schicht ersetzt durch D17/D18**

> Gilt weiter als Beschreibung des Workbooks. Für just gilt nur noch
> Gruppe 1 ohne Make-Aufruf (`just-scope.md`); Wellen 2/3 entfallen.

**Entscheidung:** **71 Kandidaten** = **44 `MIGRATE`** + **27 `BRIDGE`**.
Die übrigen **252** benannten Targets sind `OUT OF SCOPE`.

**Begründung:** Migriert wird nur, was ohne Compiler/Linker auskommt oder
dessen Make-Kontext über eine Brücke erhalten bleibt. Alles, was kompiliert,
linkt, flasht oder ein Firmware-Artefakt erzeugt, bleibt Make.

**Konsequenz:** Drei Wellen:

| Welle | Inhalt | Anzahl |
|---|---|---:|
| 1 | `MIGRATE`, Gruppe 1 — reine just-Rezeptur | 29 |
| 2 | `MIGRATE`, Gruppen 2A/2B/2C — just setzt Kontext | 15 |
| 3 | `BRIDGE` — just ruft make | 27 |

## D4 — Gruppe ≠ Disposition

**Entscheidung:** Die Taxonomiegruppe (1/2A/2B/2C/3) beschreibt die Kopplung;
die Disposition (`MIGRATE`/`BRIDGE`/`OUT OF SCOPE`/`N/A`) beschreibt die
Migrationsstrategie. Beide werden getrennt geführt.

**Begründung:** Ein Gruppe-3-Target kann migrierbar sein, wenn es nur ein
dünner Wrapper ist (`generate-Makefile.ci`). Ein 2A-Target kann eine Brücke
brauchen, wenn es den vollständigen Make-Kontext liest (`info-build`).

**Konsequenz:** Agenten dürfen nicht aus „Gruppe 3“ automatisch „OUT OF
SCOPE“ ableiten und nicht aus „2A“ automatisch „MIGRATE“.

## D5 — Brücken-Vertrag — **ersetzt durch D17** (nur noch `make <t>` → `just <t>`, nie just → make)

**Entscheidung:** `make <public-target>` ruft
`just --working-directory "$(CURDIR)" <recipe>`; ein 2A-Rezept ruft einen
privaten `_`-präfixierten Make-Helper. Kein öffentliches Make↔just-Reentry.

**Begründung:** Der App-Kontext (`BOARD`, `APPLICATION`, `BINDIR`) darf nicht
verloren gehen; der Helper-Name verhindert Rekursion.

**Konsequenz:** Jede Migration wird mit `make -n`, `just --dry-run` und einem
Byte-Vergleich (`diff <(make <t>) <(just <t>)`) geprüft.

## Offene Punkte

1. `generate-Makefile.ci` ist Gruppe 3, aber `MIGRATE` (Welle 2). Vor der
   Umsetzung entscheiden, ob die just-Rezeptur nur das Skript aufruft oder
   das Target doch `OUT OF SCOPE` wird.
2. `just` ist auf dem Arbeitsrechner derzeit nicht installiert; die
   Verifikation braucht eine gepinnte Version (zuletzt `1.59.0`).
3. Die Thesis-Referenz und `MIGRATION.md` verwenden teilweise noch das alte
   3-Tier-Modell. Dieses Protokoll und das Workbook sind für den aktuellen
   Stand maßgeblich.

---

# Nachtrag Roadmap P0 — 2026-11-12

Status-Legende: **festgelegt** (Nutzer hat entschieden) · **offen** (Vorschlag,
Entscheidung durch den Nutzer).

## D6 — Ziel und Werkzeuge je Gruppe — **festgelegt**

Die Arbeit liefert ein Migrationskonzept (Meeting 2026-11-06). Gruppe 1 →
`just`. Gruppen 2A/2B/2C/3 → CMake + Ninja empfohlen
(`riot-build-config-thesis/docs/05-migration-concept/meson-vs-cmake.md`);
in P6 werden **CMake + Ninja und Meson + Ninja** mit identischem Umfang
prototypisch umgesetzt (ein Modul + `hello-world`) und verglichen.
Die bestehenden just → `_helper`-Bridges für 2A sind Übergangslösungen.

## D7 — Wellenreihenfolge nach dem Pilot — **überholt durch D17**

Befund: Der Pilot hat 18 Welle-3-Targets (2A, `BRIDGE`) vor den restlichen
Welle-1-Targets umgesetzt (`MIGRATION.md`, Abschnitt „Mapping to the workbook
waves“).
Vorschlag: keine weiteren 2A-Bridges; zuerst Welle 1 abschließen (Doku-Targets,
`welcome`), weil Gruppe 1 das Endziel `just` hat und Gruppe 2 ohnehin zu
CMake wandert.

## D8 — Konflikt `info-files`, `info-objsize`, `info-buildsize`, `info-buildsizes-diff` — **überholt durch D17**

Workbook: `BRIDGE` (Welle 3). Pilot: bewusst Make-native.
Vorschlag: Disposition im Workbook beibehalten, im Pilot Make-native lassen
und in `MIGRATION.md` als „Ziel: CMake (2B-Artefakt-Vertrag, P6)“ führen —
eine just-Bridge brächte hier nur zusätzliche Make-Ebenen.

## D9 — `generate-features` — **geklärt durch D18: just-fähig (Gruppe 1, make-frei)**

Workbook: Gruppe 1, `OUT OF SCOPE`. Pilot: bereits als just-Rezept gebridged.
Optionen: (a) auf `MIGRATE` umklassifizieren (Kandidaten 71 → 72, Begründung im
Sheet „Verification“), (b) Bridge zurücknehmen.
Vorschlag: (a), da reines Repository-Skript ohne Kontext.

## D10 — Arbeitsstand auf `master` in `RIOT_Test` — **überholt durch D17**

Befund: `justfile` liegt untracked auf `master` ohne die Make-Bridges des
Pilot-Branches; Rezepte für 2A rufen dort nicht existierende `_helper`.
Optionen: (a) künftig auf `migration/category-1-static-introspection`
(oder einem davon abgeleiteten Branch) weiterarbeiten, (b) `master`-Kopie als
Entwurf kennzeichnen, (c) `master`-Kopie entfernen.
Vorschlag: (a). Branchwechsel/Commits führt nur der Nutzer aus.

## D11 — Klassifikationsprüfungen für P1 — **Prüfauftrag**

An `taxonomy-evidence` (P1): Ist Gruppe 1 korrekt für
- Doxygen `html`, `man`, `latex`, `check` (hängen an generiertem
  `src/changelog.md`, `doc/doxygen/Makefile:88-118`)?
- Starlight `build`, `dev`, `preview` (hängen an `install` = `npm ci`, Netzwerk,
  `doc/starlight/Makefile:6-25`)?
- `doc*` im Root (rufen `$(MAKE) -C doc/doxygen`)?

## D12 — `just` installieren — **(Vorstand, siehe unten: erledigt)**

Gepinnte Version 1.59.0 (zuletzt validiert, aktuelles Release 2026-10-15).
Download nur nach ausdrücklicher Zustimmung des Nutzers.

## D12 — `just` installieren — **erledigt 2026-11-12**

`just 1.59.0` (`just-1.59.0-x86_64-unknown-linux-musl.tar.gz`, SHA256 gegen
`SHA256SUMS` des Releases geprüft) nach `~/.local/bin/just` installiert.
`--working-directory` funktioniert in 1.59.0 ohne `--justfile`.

# Re-Validierung des Pilots — 2026-11-12 (Roadmap P0, Gate)

Methode: Pilot-Branch und seine Basis `b6d532269a` per `git archive` read-only
in ein Scratch-Verzeichnis entpackt (kein Branchwechsel). Der Pilot liegt
**592 Commits hinter** `master` `0be9299ca9`; Vergleiche gegen den sauberen
`RIOT`-Checkout sind deshalb für den Pilot nicht fair, nur gegen `b6d532269a`.
Alle 29 Rezepte bestehen `just --dry-run`.

| Kontext | Tests | Make-Bridge | `just --working-directory` |
|---|---:|---|---|
| Root: `info-boards`, `info-emulated-boards`, `info-applications`, `print-versions` | 4 | 3 PASS, `info-emulated-boards` FAIL | 2 PASS, `info-boards`/`info-emulated-boards` FAIL |
| `hello-world`, `native64`, 16 2A-Targets | 16 | 15 PASS, `info-rust` (Fehlerpfad, `cargo` fehlt) | 15 PASS, `info-rust` (Fehlerpfad) |
| `hello-world`, `samr21-xpro`, 16 2A-Targets | 16 | 13 PASS; `info-rust` (Fehlerpfad), `info-build` (nur Zeitstempel in `TERMFLAGS`), **`info-features-required` FAIL** | 14 PASS; `info-rust`, `info-build` (Zeitstempel) |

## D13 — Bridge leakt Make-Zustand (Blocker) — **behoben im Worktree, mit D17 gegenstandslos**

`make BOARD=samr21-xpro info-features-required` liefert über die Bridge
zusätzlich `newlib`; direkt über `just` bzw. `_info-features-required` ist die
Ausgabe korrekt (2× reproduziert). Ursache: Der Eltern-`make` exportiert
berechneten Zustand an `just` → Kind-`make`, das daraus eine andere
Abhängigkeitsauflösung ableitet (`sys/Makefile.dep:206-212`, `newlib_nano`).
Nur `info-build`/`info-build-json` nutzen `env $(JUST_CONTEXT_UNEXPORT)`
(`Makefile.include:1092`). Mit dieser Bereinigung ist die Ausgabe korrekt
(geprüft). Vorschlag: `env $(JUST_CONTEXT_UNEXPORT)` in **alle**
2A-Bridges aufnehmen und Paritätstests immer auch für ein Hardware-Board
fahren.

## D14 — Gruppe-1-Rezepte direkt über just nicht byte-gleich — **behoben 2026-11-12 (uncommitted, Worktree `RIOT_Test-pilot`)**

`info-boards`, `info-emulated-boards`: (a) Leerzeichen vor dem Zeilenende
(`… | tr '\n' ' '; echo`), (b) `sort -u` sortiert nach Locale, Makes
`$(sort)` byteweise (z. B. `atxmega-a1-xplained`). Bei `info-emulated-boards`
ist auch die Make-Bridge betroffen. Vorschlag: `LC_ALL=C sort -u` und
Ausgabe ohne nachgestelltes Leerzeichen (z. B. `paste -sd' '`).
Nicht-Abweichungen: Zeitstempel in `TERMFLAGS`, Fehlerpfade mit zusätzlichem
Bridge-Frame (`info-rust`, Root-`help` über `.DEFAULT`).

Nachweis für D13/D14: `test-logs/2026-11-12-fix-d13-d14.md`.

## D15 — Doppelter Alias-Hinweis bei `BOARD=native` — **mit D17 gegenstandslos**

Über eine kontextabhängige Bridge erscheint
`using BOARD="native64" as "native" on a 64-bit system` zweimal auf stderr
(stdout identisch). Ursache: `BOARD=native` steht über `MAKEFLAGS` auch im
Kind-`make`, das den Alias erneut auflöst (`makefiles/board_alias.inc.mk:30`).
Bestand schon vor dem Fix. Optionen: (a) als erlaubte stderr-Abweichung
dokumentieren, (b) Hinweis im Kind-`make` per Marker-Variable unterdrücken
(Änderung an RIOT-Kerndatei). Vorschlag: (a) für den PoC.

## D16 — Boards im Proof of Concept — **festgelegt**

Nur `native64` und `native` (Nutzer, 2026-11-12). Weitere Boards (Hardware)
werden später entschieden. Hinweis: D13 trat nur auf `samr21-xpro` auf —
Hardware-Boards decken Fehler auf, die `native` nicht zeigt.

## D17 — just nur für Gruppe 1, kein `make` in just — **festgelegt (Nutzer, 2026-11-12)**

Wortlaut sinngemäß: Ziel der Migration ist, Verantwortung aus Make
herauszulösen. Targets der Gruppen 2A/2B/2C/3 in just zu schreiben (just →
`make _helper`) baut nur eine Oberfläche für Make und ist nicht akzeptabel.
just darf nur Targets enthalten, die nichts mit Make, Kontext, Artefakten,
Laufzeit oder Artefakt-Lebenszyklus zu tun haben (Gruppe 1). Externe
Host-Werkzeuge sind innerhalb von Gruppe 1 erlaubt; 2A/2B-Targets mit
externem Dienst (`iotlab-*`, `git-download`, `esptool`, `openv-*`) nicht.
`make <t>` → `just <t>` bleibt als Übergang erlaubt.

Folgen:
- Workbook-Dispositionen `MIGRATE`/`BRIDGE` für 2A/2B/2C/3 (Wellen 2/3,
  42 Targets) gelten für just nicht; Workbook bleibt unverändert (read-only).
- Pilot-Branch `migration/category-1-static-introspection` = verworfener
  Ansatz, nur Gegenbeispiel. Gearbeitet wird im Working Tree von `RIOT_Test`
  auf `master`, nur eigene uncommittete Änderungen.
- Überholt: D7 (Wellenreihenfolge), D8 (`info-files`/Größen-Konflikte, bleiben
  Make-nativ), D10 (Arbeitsstand: geklärt), D13 (Bridge-Leck; Fix im Worktree
  gegenstandslos), D15 (Alias-Hinweis über Bridge). D14 bleibt relevant für
  die Gruppe-1-Rezepte.
- Agents/Skills angepasst (`CLAUDE.md` Regel 9, `riot-make-to-just`,
  `migration-review`, `migration-concept`, `migration-lead`, `architect`,
  `developer`, `auditor`, `reviewer`, `tester`, `writer`, `scout`).

## D18 — Quellcode-Prüfung aller 57 Gruppe-1-Targets — **festgelegt 2026-11-12: `doc-ci` und `static-test` bleiben vorerst in Make**

Details: `just-scope.md`. Kurz: 28 `MIGRATE` rein make-frei umsetzbar
(Doku-Targets müssen zwei Make-Ebenen in einer Rezeptur auflösen);
8 `OUT OF SCOPE` sind doch just-fähig (`generate-*`, `riotgen-installed`,
`generate-features`); 15 Make-Funktionstests bleiben in Make (Nutzer).
**Entschieden (Nutzer, 2026-11-12): beide bleiben vorerst in Make.**
- `doc-ci` — kann doxygen aus dem Quellcode bauen (Host-Build = Gruppe 3);
  Vorschlag: just nur mit vorinstalliertem doxygen, Bereitstellung abtrennen.
- Root-`static-test` — Unterprüfungen rufen `make` auf (Feature-Resolution-,
  Boards-supported-Tests, `generate-features`); Vorschlag: bleibt in Make, bis
  diese Prüfungen zur Build-/Konfig-Schicht wandern.
**Umklassifizierungsvorschläge (Workbook-Pflege über `data-analyst`):**
`download_binary` → 2A (+2C-Voraussetzung), `bin`/`mock_suit_sec`/
`warn_release_tests` → Teil von Gruppe 3 bzw. 2B.

## D19 — Umsetzung der just-Schicht (Roadmap P3) — **umgesetzt 2026-11-12, committet 2026-11-13 (Branch `migration/just-group1-extraction`)**

Freigabe Nutzer 2026-11-12: „Fange mit der Umsetzung an … nur Targets, die
nach Vorschriften in just geschrieben werden können.“

- Alle 36 Targets aus `just-scope.md` A+B laufen im Wurzel-`justfile`, ohne
  `make`-Aufruf; die Make-Deklarationen sind einzeilige Weiterleitungen
  (`@just --justfile "$(_RIOT_JUSTFILE)" <recipe>`, Pfad relativ zum
  Makefile). 7 getrackte Dateien geändert; Make-Logik dieser Targets entfernt.
- Namensschema: Rezepte aus `doc/doxygen`/`doc/starlight` heißen
  `doxygen-<t>`/`starlight-<t>` (Kollisionen wie `build`, `check`,
  `security`); `doxygen-version`, `graphviz-check` und alle übrigen behalten
  den Make-Namen.
- `.DEFAULT` leitet ebenfalls an `just welcome` weiter (keine doppelte
  Willkommens-Nachricht mehr in Make).
- Übergabe von Variablen: nur Nutzereingaben; von Makefiles abgeleitete
  Werte nie (`BOARDSDIRS` nur bei Herkunft Umgebung/Kommandozeile vor dem
  Einlesen, `APPLICATION_DIRS`/`EMULATED_BOARDS`/`DOCUMENTATION_FORMAT` nur
  von der Kommandozeile).
- Bekannte Abweichungen V1–V18 und Nachweise:
  `test-logs/2026-11-12-p3-group1-just.md`.
- Voraussetzung vor Upstream: `just` in allen CI-Images (getestet 1.59.0).
- Bekannte Doppelungen mit Make, bewusst belassen: `DOXYGEN_MIN_VERSION`
  (für `doc-ci`), Starlight-`install` (Name gehört zu Gruppe 2C). Beide mit
  „keep in sync“-Kommentar auf beiden Seiten.

## D20 — Vollständige Auslagerung aus Make — **umgesetzt 2026-11-12, committet 2026-11-13 (`f6e2445482`, Fixes `8a39e8ebb9`)**

Nutzer: (1) migrierte Targets haben keinen Eintrag mehr in Make, (2) ihre
Funktion ändert sich nicht, (3) zentrale Konfigurationsdatei, (4) justfile je
Kategorie aufteilen. Rückfragen entschieden:
- Aufrufer in RIOT (Skripte, CI, `.murdock`, GitHub-Workflows) auf just umstellen;
  Workflows bekommen einen Installationsschritt (`taiki-e/install-action@v2`,
  just 1.59.0).
- `make` im Root gibt einen kurzen Hinweis auf `just --list`; der Willkommenstext
  liegt nur in just und nennt just-Befehle.
- Zentrale Konfiguration = eine Datei für die just-Schicht (`just/settings.just`);
  Make liest benötigte Werte per `just --evaluate`.
- Aufteilung per `import` (Namen unverändert).
- Kein App-Kontext: Eingaben werden explizit übergeben.
- Dokumentation auf just umgeschrieben (Release-Notes/Changelog unverändert).

Damit entfallen die Weiterleitungs-Regeln aus D17/D19 (Make → just als
Übergang). Abweichungen W1–W14 im Testprotokoll.

## D21 — Konfigurations-Schicht (Roadmap P4) — **entschieden 2026-11-13**

Grundsatz des Nutzers: **Make wird am Ende durch neue Werkzeuge ersetzt**; es
wird keine Makefiles und keine Make-Abhängigkeiten mehr geben. Die zentrale
Konfigurationsdatei ist deshalb die maßgebliche Quelle; jede Make-Anbindung
ist nur Übergang, bis die Build-Werkzeuge aus P6 (CMake bzw. Meson) die
Datei direkt lesen.

Entscheidungen (Rückfragen 2026-11-13):
- Format **YAML** (Vorbild `features.yaml`, PyYAML vorhanden).
- Umfang des ersten PoC: **alle Eingaben, ohne Bedingungen**
  (`hello-world`, `gnrc_networking`; `native64`/`native`); Bedingungen wie
  `USE_ZEP` und Includes nach `Makefile.include` bleiben vorerst als Rest im
  App-Makefile.
- Make-Anbindung (Übergang): **generierte, eingecheckte `.inc.mk`**, die das
  App-Makefile inkludiert; ein CI-Check prüft, dass sie aktuell ist
  (Muster `features.yaml` → `features_existing.inc.mk`).
- Vorrang **wie heute**: der Generator erzeugt `?=` bzw. `+=`; Umgebung und
  Kommandozeile überschreiben weiterhin.
- **Abhängigkeitsauflösung nicht in P4**: Make löst übergangsweise auf; ein
  tool-unabhängiger Resolver (Modul-Abhängigkeiten als Daten statt
  `Makefile.dep`) kommt in P6 mit den Build-Werkzeugen.
- Schema: **JSON Schema**, geprüft im Generator; der Nutzer erlaubt, dafür
  nur die nötige Bibliothek (`jsonschema`) zu installieren.
- Ort: **je App, eigener Dateiname** (z. B. `riot-app.yaml`). Kconfig bleibt
  unangetastet; ob Kconfig die Datei mit aufgreift, ist laut Nutzer kein
  Problem, da Kconfig nicht ersetzt werden soll.
- just liest weder aufgelösten Zustand noch die App-Konfiguration (D17).

Grundlage: `config-analysis.md`, Baseline `p4-baseline/`.

Nachtrag D21 (Rückfragen nach der Umsetzung, 2026-11-13):
- CI-Check `check_riot_app_config_up_to_date.sh` wird in `static_tests.sh`
  eingehängt; `jsonschema` wird (wie `just`) als Voraussetzung für die
  CI-Images dokumentiert.
- Pflichtfeld `schema_version: 1` in jeder `riot-app.yaml`; der Generator
  lehnt unbekannte Versionen ab.
- App-Makefiles brechen mit klarer Meldung ab, wenn `riot-app.inc.mk` fehlt.
- Kein SPDX-Kopf in YAML/JSON (wie in RIOT üblich); SPDX nur bei `.py`/`.sh`.
- Zusätzliches just-Rezept `generate-app-config` (`just-scope.md`, Abschnitt F).
- Präzisierung zu "just liest … nicht die App-Konfiguration": just selbst
  liest sie nie; das repo-weite Generator-Rezept `generate-app-config` ruft
  ein Python-Werkzeug auf, das sie liest (dieselbe Ausnahme wie
  `generate-features` mit `features.yaml`).

## D22 — Termin 2026-11-13: Board nRF52840, reproduzierbare Kategorisierung, Tool-Vergleich je Kategorie — **festgelegt (Betreuung, 2026-11-13; übernommen 2026-11-14)**

Quelle: `riot-build-config-thesis/docs/00-project/meeting-notes.md`
(Abschnitt 2026-11-13).

1. **Board:** Die Arbeit wird auf **nRF52840** begrenzt (ersetzt D16
   `native64`/`native` als Ziel-Board). Grund laut Termin: auf `native` haben
   viele Targets keine Bedeutung (kein board-spezifisches Bauen, kein
   Flashen/Debuggen). Die Begrenzung muss in der Arbeit begründet werden
   (z. B. zeitlicher Aufwand) und es muss beschrieben werden, was bei der
   Migration weiterer Boards passiert (Übertragbarkeit).
   **Nutzer 2026-11-14: Board `nrf52840dk`, keine Hardware vorhanden.**
   Hardwareabhängige Targets werden deshalb gebaut/statisch geprüft, ihr
   Lauf auf dem Board als "nicht ausgeführt (keine Hardware)" protokolliert
   und als Begrenzung der Arbeit begründet. Toolchain (`arm-none-eabi-gcc` fehlt auf dem Host; `docker` vorhanden →
   `BUILD_IN_DOCKER=1`).
2. **Kategorien reproduzierbar:** Die Einteilung 1/2A/2B/2C/3 ist Grundlage
   und muss reproduzierbar sein (Skript mit festen Regeln statt manueller
   Zuordnung; gleiche Eingabe → gleiches Ergebnis).
3. **Neue Targets:** Es muss geprüft werden, dass neu hinzugefügte Targets
   automatisch kategorisiert werden und funktionsfähig sind (z. B. CI-Check,
   der unklassifizierte Targets meldet).
4. **Tool-Vergleich:** 2–3 Tools vergleichen ("welche gibt es überall, welche
   ist sinnvoller"); je Kategorie 2–3 Beispiel-Targets, deren Auswahl
   begründet wird.
5. **Begrenzungen** müssen jeweils aussagekräftig begründet sein; sie müssen
   nicht in der Forschungsfrage stehen, aber in der Ausarbeitung klar sein.
   Die Forschungsfrage wird an die neuen Beschränkungen angepasst.
6. **Umgebungsänderungen:** prüfen, was passiert, wenn sich die Environments
   ändern. Nutzer 2026-11-14: gemeint ist die Umgebung aus
   `riot-build-config-thesis/experiments/environment/environment.md`
   (Host-Maschine: OS, Kernel, CPU, RAM; Software: Make, Git, Python, GCC,
   just, CMake, Ninja, Meson, Toolchain/Docker). Beispiel schon jetzt: Kernel
   dort 7.0.0-38, auf dem Host inzwischen 7.0.0-43.
7. **Hardwareabhängige Targets** identifizieren; sie müssen nach der Migration
   auf dem Board getestet werden.

Folgen:
- D16 ist für neue Arbeit überholt. P3 (Gruppe 1, board-unabhängig) bleibt
  gültig; P4 (`native`) wird für nRF52840 wiederholt bzw. ergänzt.
- Agents/Skills/CLAUDE.md angepasst (2026-11-14): `CLAUDE.md` Regel 7,
  `taxonomy-evidence`, `tool-evaluator`, `tester`, `migration-lead`,
  `concept-architect`, Skills `taxonomy-evidence`, `tool-evaluation`,
  `migration-concept`, `riot-make-to-just`; Thesis-Repo `CLAUDE.md`,
  `thesis-writing`, `thesis-writer`, `thesis-reviewer`.

## D23 — Reproduzierbare Kategorisierung (D22 Punkte 2/3) — **entschieden 2026-11-14, umgesetzt (uncommittet)**

Nutzer (Rückfrage 2026-11-14): Methode **Regeln + Make-Datenbank**, Ort
**`RIOT_Test/dist/tools`** mit CI-Hook.
- `dist/tools/target_taxonomy/target_taxonomy.py`: Workbook-Regeln als Code
  (Regel-IDs B1–B7, L1, R1, K1–K3, S0/S1, N0), Kontext `BOARD=nrf52840dk`,
  Fallback `native64`; deterministisch (zwei Läufe byte-gleich).
- Ergebnis gegen die 323 Workbook-Targets nach dem Review: Übereinstimmung
  0,789, Cohens κ 0,704 (vorher 0,749/0,650; Testlog
  `2026-11-14-target-taxonomy-rules.md`). Die 68 Abweichungen sind Eingabe
  für die Klärung in P1 (zweiter Kodierer).
- `check-new` prüft neue Targets zusätzlich per `make -n` (Make akzeptiert
  das Target im Kontext); Exit 0/1/2.
- `check-new` + `dist/tools/ci/check_new_make_targets.sh` (in
  `static_tests.sh`): neue Targets seit `CI_BASE_BRANCH` werden automatisch
  klassifiziert; CI schlägt fehl, bis sie in `inventory.csv` stehen.

## D24 — Beispiel-Targets und Tool-Vergleich je Kategorie — **entschieden 2026-11-14 (Nutzer)**

Grundlage: `riot-build-config-thesis/docs/05-migration-concept/examples-and-tools.md`
(Kriterien E1–E6, Verfügbarkeit Ubuntu 24.04 und riotbuild-Image).
- Beispiele: 1 = `doc`, `generate-features`, `list-ttys`;
  2A = `info-modules`, `info-features-used`, `info-cpu`;
  2B = `info-buildsize`, `flash-only`, `term`; 2C = `clean`, `distclean`;
  3 = `all`, `flash`, `test`. Hardware-Targets ohne Board: gebaut/Dry-Run,
  Board-Lauf "nicht ausgeführt".
- Tools hands-on: Task-Schicht Make, just, Task (go-task); Konfiguration
  Make-Variablen vs. `riot-app.yaml` (Kconfig nur aus der AHP-Bewertung);
  Build Make, CMake + Ninja, Meson + Ninja (im riotbuild-Image).

## D25 — Nutzerentscheidungen 2026-11-14: Forschungsfragen, Board-Gründe, Resolver

- **Forschungsfragen:** Vorschlag vom 2026-11-14 (`thesis/Masterthesis-copy/notes/rq-proposal-2026-11-14.md`)
  bestätigt; kann später erneut angepasst werden.
- **Gründe für `nrf52840dk`** (alle belegt in RIOT `0be9299ca9`): auf `native`
  haben viele Targets keine Bedeutung (Termin); Zeitaufwand; Übertragbarkeit
  (16 der 298 Boards mit `CPU_MODEL = nrf52840`); Funktionsumfang (91 Features,
  u. a. BLE, IEEE 802.15.4, USB-Device, ADC/I2C/SPI/PWM/UART/Timer); mehrere
  Programmer (bmp, jlink, openocd); ARM-Toolchain im gepinnten riotbuild-Image.
- **P6-Abweichung** (ganze Apps statt erst ein Modul, Make ruft das Build-Tool
  nicht auf) akzeptiert. **Regel:** vor Abweichungen vom Plan und vor
  Designentscheidungen den Nutzer fragen.
- **Resolver (P6, S2-Ende):** Abhängigkeiten als Daten + Python-Resolver
  (Fixpunkt), halbautomatisch aus `Makefile.dep`/`Makefile.features`
  übersetzt; Umfang hello-world **und** gnrc_networking auf `nrf52840dk`;
  Parität mit `info-modules`/`info-features-used`/`info-packages`.
- Nachtrag D25 (Rückfrage Resolver-Design, 2026-11-14): Auswertung in
  **Make-Reihenfolge** (Include-Reihenfolge, Durchläufe bis stabil;
  Reihenfolge-Abhängigkeit wird als Befund dokumentiert); **Übersetzer für
  alle 720 `Makefile.dep`** mit Zählung der nicht übersetzbaren Konstrukte;
  Ort **`build-poc/resolver`**, Ausgabe ersetzt Makes Export in `run_poc.sh`.

## D26 — Build ohne Make: Flags, Quellen, Vorstufen (Teil A) — **entschieden und umgesetzt 2026-11-14 (uncommittet)**

- **Flags** (CFLAGS, INCLUDES, LINKFLAGS, Linker-Skript): die eingebundenen
  `Makefile.include` werden wie beim Resolver in Datenregeln übersetzt und
  nach der Auflösung ausgewertet; `$(shell …)`-Aufrufe als benannte
  Python-Bausteine.
- **Quellen je Modul:** Modul-`Makefile` (MODULE, SRC, NO_AUTO_SRC,
  SUBMODULES, DIRS) mit demselben Übersetzer; `*.c`-Suche wie `Makefile.base`
  in Python.
- **Vorstufen** (Paket-Downloads nach `build/pkg`, `riotbuild.h`,
  `preprocessor_successor.h`): **vorhandene RIOT-Skripte direkt aufrufen**
  (`genconfigheader.sh`, `generate_pp_successor_header.sh`, Git-Fetch/Patch
  wie `pkg/pkg.mk`), gesteuert vom Resolver-Ergebnis; nur der Ablauf ist neu.
- **Umfang:** zuerst hello-world auf `nrf52840dk`; danach Entscheidung über
  gnrc_networking.
- Ergebnis D26 (Testlog `2026-11-14-build-without-make.md`): hello-world auf
  `nrf52840dk` baut in einem frischen Klon ohne Make; Firmware-Image von
  CMake + Ninja und Meson + Ninja byte-identisch zum Make-Build. Für die
  Vorstufen gibt es in RIOT keine eigenständigen Skripte, nur Rezepte:
  `prestep.py` führt sie als minimaler Rezept-Ausführer aus (Befehle
  unverändert, rekursives `$(MAKE)` aus den übersetzten Regeln).

## D27 — Make-unabhängiges Format für Abhängigkeitsregeln — **entschieden 2026-11-14 (Nutzer)**

- **Ablage:** je Modul (Verzeichnis mit `Makefile.dep`) eine YAML-Datei neben
  der `Makefile.dep`.
- **Rolle:** YAML ist **maßgeblich**; `Makefile.dep` wird daraus generiert und
  eingecheckt (Make-Adapter, Muster `features.yaml` → `features_existing.inc.mk`
  und `riot-app.yaml`, D21); CI-Check auf Aktualität; der Resolver liest die
  YAML direkt.
- **Umfang PoC:** die `Makefile.dep`, die hello-world auf `nrf52840dk` liest;
  der Rest bleibt Make-Syntax. Parität: Auflösung mit generierten
  `Makefile.dep` = Original (Make und Resolver), gnrc_networking als Gegenprobe.

## D28 — Hands-on-Scores übernommen — **entschieden 2026-11-14 (Nutzer)**

Die Neuberechnung (`riot-build-config-thesis/docs/05-migration-concept/evaluation/results-handson-2026-11-14.md`)
wird übernommen: 6 geänderte Werte (Task K1 2→3, K5 1→2; Meson G7 3→2,
G9 2→3, in S2 G2 2→3, G4 1→2); Rang 1/2 unverändert (just, YAML, CMake);
AHP-Gewichte bleiben bis zum Paarvergleich mit dem Betreuer.
Konfigurations-/Startzeit bleibt **Stresstest**, kein eigenes Kriterium.
- Ergebnis D27 (Testlog `2026-11-14-deps-yaml.md`): 17 Dateien nach YAML
  exportiert (6 Regeln bleiben markierte Make-Ausdrücke), `Makefile.dep`
  daraus generiert; Make-Auflösung 12/12 identisch, Resolver liest die YAML
  (10/10 identisch), Build-Zustand beider Apps unverändert; CI-Check und
  `just generate-deps`.
- Nachtrag D27 (Nutzer, 2026-11-15): auch die 13 zusätzlichen
  Abhängigkeitsdateien von gnrc_networking nach YAML (30 von 756 Dateien);
  Parität unverändert (Testlog `2026-11-14-deps-yaml.md`). Leichtere
  Review-Befunde des Resolvers behoben (`2026-11-14-build-without-make.md` §8).
