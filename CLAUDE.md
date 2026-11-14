# CLAUDE.md — RIOT_Test (Masterthesis: Migrationskonzept von GNU Make)

@AGENTS.md

## Worum es hier geht

`RIOT_Test` ist die **Experimentier-Arbeitskopie** von RIOT für die Masterarbeit
in `/home/mohammadjavad/Documents/riot-build-config-thesis`. Ziel der Arbeit ist
ein **Migrationskonzept** für RIOTs Make-basiertes Build- und
Konfigurationssystem (Meeting 2026-11-06): beschreiben, *wie* man vorgeht —
Umsetzung in `RIOT_Test` ist ein Proof of Concept, das das Konzept belegt, nicht
das Ziel selbst.

Leitfrage (Stand 2026-10-23):
> Which responsibilities of RIOT's Make-based development tooling can be
> separated from the core build process and delegated to purpose-specific tools
> without compromising functionality or configuration consistency?

Drei Schichten des Konzepts — nie vermischen:

| Schicht | Inhalt | Werkzeug (Stand) |
|---|---|---|
| Task-/Kommando-Schicht | **nur** Gruppe 1 (stateless: `info-boards`, `doc`, `welcome`, …), Liste in `.claude/research/just-scope.md` | `just` (festgelegt), **ohne jeden make-Aufruf** |
| Konfigurations-Schicht | `BOARD`, `USEMODULE`, Features, Defaults, `?=`-Kaskade | zentrale, tool-unabhängige Konfiguration (offen) |
| Build-Schicht | Gruppen 2A/2B/2C/3 (Kontext, Artefakte, Laufzeit, Lebenszyklus, Build) | GNU Make heute (unverändert); Ziel CMake + Ninja (Vergleich mit Meson: `docs/05-migration-concept/meson-vs-cmake.md`) |

## Harte Regeln

1. **Nichts committen, pushen, mergen, rebasen oder taggen.** Der Nutzer prüft
   jede Änderung selbst. Änderungen bleiben im Working Tree; am Ende
   `git status` und `git diff --stat` berichten. (Technisch per
   `.claude/settings.json` gesperrt.)
2. `/home/mohammadjavad/Documents/RIOT` ist der **saubere Referenz-Checkout**
   (master `0be9299ca9`). Dort nur lesen und `make`-Beobachtungen ausführen,
   niemals editieren.
3. Thesis-Repo: Konzept-/Thesis-Texte gehören nach
   `riot-build-config-thesis/docs/`; die Workbook-Kopie unter
   `docs/04-make-targets/` ist read-only.
4. Zahlen nie aus dem Gedächtnis: Workbook `riot_all_make_targets.xlsx` ist die
   Quelle (2.314 Deklarationen / 323 benannte / 71 Kandidaten = 44 `MIGRATE` +
   27 `BRIDGE` / 252 `OUT OF SCOPE`). Gruppe (1/2A/2B/2C/3) ≠ Disposition.
   Die Dispositionen gelten für die just-Schicht nur noch, soweit Regel 9
   sie zulässt.
5. Wissenschaftliche Aussagen: nur verifizierte Quellen (DOI via Crossref),
   Kennzeichnung `[source]` / `[observation]` / `[inference]`.
6. Antworten an den Nutzer auf Deutsch; Fachbegriffe/Titel im Original.
7. **Ziel-Board: `nrf52840dk`** (Termin 2026-11-13 + Nutzer 2026-11-14, D22;
   ersetzt D16 `native64`/`native`). **Keine Hardware vorhanden:** nie
   flashen; Hardware-Tests als "nicht ausgeführt" protokollieren, nie als
   bestanden. Toolchain fehlt auf dem Host → `BUILD_IN_DOCKER=1` (Download
   des Images nur nach Freigabe). `native64` bleibt nur als
   Vergleich/Referenz für bereits erledigte Arbeit (P3/P4). Jede Begrenzung
   wird begründet; die Übertragbarkeit auf andere Boards wird beschrieben.
8. Gearbeitet wird im Working Tree von `RIOT_Test` auf `master`; dort dürfen
   nur eigene, uncommittete Änderungen dieses Projekts stehen. Der Pilot-Branch
   `migration/category-1-static-introspection` (just → `_helper`-Bridges für
   2A/2C) ist ein **verworfener Ansatz** und nur Gegenbeispiel.
9. **Ziel der Migration: Verantwortung aus Make herauslösen, nicht just als
   Oberfläche auf Make bauen** (Nutzerregel 2026-11-12, D17):
   - In just kommen nur Gruppe-1-Targets (kein Kontext, kein Artefakt, keine
     Laufzeit, kein Artefakt-Lebenszyklus, kein Build) —
     `.claude/research/just-scope.md`.
   - Eine just-Rezeptur ruft **nie** `make`/`_helper` auf, auch nicht über
     ein Skript.
   - Ausgelagerte Targets haben **keinen Eintrag mehr in Make** (keine Regel,
     keine Weiterleitung); RIOTs Aufrufer und Doku nutzen `just` (D20).
   - Alle Einstellungen der just-Schicht stehen zentral in
     `just/settings.just`; Rezepte nach Gruppe in `just/<gruppe>.just`.
   - Gruppen 2A/2B/2C/3 kommen nie in den justfile, auch wenn das Workbook
     `MIGRATE`/`BRIDGE` sagt; sie bleiben Make-nativ bis zur Build-Schicht (P6).

## Wichtige Orte

- Konzept & Roadmap: `riot-build-config-thesis/docs/05-migration-concept/`
  (`tool-evaluation.md`, `roadmap.md`, `references.bib`)
- Forschungsnotizen der Agenten: `.claude/research/`
- just-Umfang: `.claude/research/just-scope.md` (einzige Quelle)
- Verworfener Pilot: `MIGRATION.md`, Branch
  `migration/category-1-static-introspection` (nur lesen)
- Agenten: `.claude/agents/`, Skills: `.claude/skills/`
  (`.opencode/` ist das Original für OpenCode und bleibt unverändert)

## Agenten-Überblick

| Agent | Zweck |
|---|---|
| `migration-lead` | koordiniert Phasen/Wellen, Gates, Zahlenkonsistenz |
| `concept-architect` | schreibt/prüft das Migrationskonzept (Schichten, Muster, Verträge) |
| `tool-evaluator` | wissenschaftliche Tool-Bewertung (DESMET + AHP, Sensitivität) |
| `config-analyst` | Konfigurationsquellen analysieren, zentrale Konfig-Datei entwerfen |
| `architect` | Blueprints und Architekturregeln für die just-Schicht (nur Gruppe 1) |
| `scout` | extrahiert Rezepte verbatim mit `file:line` |
| `developer` | setzt freigegebene Gruppe-1-Targets make-frei in just um (ohne Commit) |
| `auditor` / `reviewer` / `tester` | statische Prüfung / Review / Laufzeit-Parität |
| `writer` | `MIGRATION.md`, Mapping-Tabellen, Onboarding |
| `data-analyst` | Workbook und Inventar |
| `taxonomy-evidence` | Validierung der 1/2A/2B/2C/3-Taxonomie |
| `explainer` | erklärt Code, ändert nichts |

## Arbeitsweise mit dem Nutzer (Nutzerregeln 2026-11-13)

1. Berichte an den Nutzer sind **kurze Zusammenfassungen** dessen, was gemacht
   wurde (Ergebnis, Status, offene Entscheidungen) — keine Detailprotokolle;
   Details stehen in Testlogs/Notizen.
2. **Modell und Denkstufe nach Komplexität wählen:** Suche/Extraktion →
   haiku/low; Prüfen, Zählen, Doku, Quellen → sonnet/medium; Entwurf,
   Umsetzung, Review, Wissenschaftstext → inherit (opus)/high. Die Agenten
   haben dafür `model:`/`effort:` im Frontmatter; beim Start eines Agenten
   bei Bedarf überschreiben.
3. **Nicht auf irrelevante Agenten warten:** Arbeit, die nicht vom Ergebnis
   eines laufenden Agenten abhängt (z. B. ein vom Nutzer freigegebener Commit),
   sofort erledigen.
4. **Nach jedem abgeschlossenen Task eine Push-Benachrichtigung** an den
   Nutzer senden (kurz: was fertig ist, was er entscheiden/delegieren kann).
5. **Usage-Limit:** Ist das Usage-Limit wieder erreicht, anhalten und den
   Nutzer fragen, ob weitergemacht werden soll (Nutzerregel 2026-11-14).

## Vorgaben aus dem Termin 2026-11-13 (D22)

1. **Board nRF52840** statt `native` (Begründung + Übertragbarkeit auf andere
   Boards in der Arbeit).
2. **Kategorien 1/2A/2B/2C/3 reproduzierbar** (regelbasiertes Skript, gleiche
   Eingabe → gleiches Ergebnis); **neue Targets automatisch kategorisieren**
   und auf Funktionsfähigkeit prüfen (CI-Check).
3. **Tool-Vergleich: 2–3 Tools**, je Kategorie **2–3 Beispiel-Targets** mit
   begründeter Auswahl.
4. **Jede Begrenzung aussagekräftig begründen**; Forschungsfrage an die
   Beschränkungen anpassen (Eingrenzungen in der Arbeit, nicht zwingend in der
   Frage).
5. Prüfen: **Verhalten bei geänderten Environments** (Host + Software laut `riot-build-config-thesis/experiments/environment/environment.md`); **hardwareabhängige
   Targets** identifizieren und nach der Migration auf dem Board testen.
