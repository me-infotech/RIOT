# Research Workspace — RIOT Make-Targets

> **Hinweis 2026-11-12 (D17):** Die Dispositionen `MIGRATE`/`BRIDGE` und die
> Wellen 2/3 unten beschreiben das Workbook. Für die just-Schicht gilt nur
> noch Gruppe 1 ohne jeden `make`-Aufruf; maßgeblich ist `just-scope.md`.

Dieser Ordner ist der schreibbare Ausgabebereich der Agenten
`taxonomy-evidence` und `data_analyst`. Er enthält die evidenzbasierte
Grundlage der Make→just-Migration. Der Agent hat **kein** Schreibrecht am
RIOT-Quellbaum, an der Thesis oder am Referenz-Workbook.

## Verbindliche Zahlen (2026-11-09, RIOT master `0be9299ca9`)

Das Inventar hat drei Ebenen. Sie dürfen nicht vermischt werden:

| Ebene | Anzahl | Bedeutung | Verwendung |
|---|---:|---|---|
| **Deklarationen** | **2.314** | Jede im Repo gefundene Target-Deklaration (inkl. `CLEAN--*`, Datei-/Pfadziele, Pattern-/Modul-/Spezialziele, variablen-expandierte Ziele). | Nur Referenz/Vollständigkeit. **Kein** Migrationsumfang. |
| **Benannte Targets** | **323** | Stabil benennbare, aufrufbare Targets mit eigenem Rezept. | Arbeitsgrundlage und Klassifikationsuniversum. |
| **Migrationskandidaten** | **71** | Davon **44 `MIGRATE`** + **27 `BRIDGE`**. | Tatsächlicher Migrationsumfang. |

Die kanonische 87er-`help`-Liste ist nur eine Teilmenge der 323:
`87 kanonisch + 215 zusätzliche + 21 netto neu = 323`.

### Klassifikation der 323 benannten Targets

| Gruppe | Name | Anzahl |
|---|---|---:|
| 1 | Stateless / kein Build | 57 |
| 2A | Kontextabhängig, kein Build | 52 |
| 2B | Artefakt-/laufzeitabhängig, kein Build | 44 |
| 2C | Artefakt-Lebenszyklus, kein Build | 12 |
| 3 | Build erforderlich | 158 |
| **Gesamt** | | **323** |

Die kanonische 87er-Teilmenge verteilt sich auf `1/2A/2B/2C/3 = 6/27/20/4/30`.

### Disposition (orthogonal zur Gruppe)

| Disposition | Anzahl | Bedeutung |
|---|---:|---|
| `MIGRATE` | 44 | Rezept wird nach just überführt; `make <target>` bleibt als Brücke erhalten. |
| `BRIDGE` | 27 | just-Rezeptur delegiert an make, weil make-berechneter Zustand nötig ist. |
| `OUT OF SCOPE` | 252 | Benanntes Target außerhalb des Migrationsumfangs (Build, Flash, Artefakt-Erzeugung). |
| `N/A` | 1.991 | Keine benannte Zielscheibe (generierte/intern/Datei-/Pattern-Ziele). |

**Wichtig:** Gruppe und Disposition sind orthogonal. Ein Target der Gruppe 3
kann `MIGRATE` sein, wenn es nur ein dünner Orchestrierungs-Wrapper ist
(Beispiel: `generate-Makefile.ci` ruft ein Skript auf, das pro Board baut).
Umgekehrt kann ein 2A-Target `BRIDGE` sein, wenn es den vollständigen
Make-Kontext braucht.

### Wellen

| Welle | Umfang | Anzahl |
|---|---|---:|
| 1 | `MIGRATE`, Gruppe 1 — reine just-Rezeptur | 29 |
| 2 | `MIGRATE`, Gruppen 2A/2B/2C — just setzt Kontext, ruft bestehende Logik | 15 |
| 3 | `BRIDGE` — just→make | 27 |
| **Gesamt** | | **71** |

Die konkrete Target-Liste steht in [`migration-scope.md`](migration-scope.md)
und im Sheet „Migration Candidates“ des Workbooks.

## Referenzen

- Verbindliches Workbook:
  `/home/mohammadjavad/Documents/RIOT_Test/riot_all_make_targets.xlsx`
  (7 Sheets: Summary, Named Targets, Migration Candidates, Group & Category
  Definitions, Method & Scope, Source Inventory, Verification).
- Thesis-Kopie:
  `/home/mohammadjavad/Documents/riot-build-config-thesis/docs/04-make-targets/riot_all_make_targets.xlsx`
  — nicht verändern.
- Sauberer Make-Checkout für Beobachtungen:
  `/home/mohammadjavad/Documents/RIOT` (master, `0be9299ca9`).
- Migrationsregeln: Skill `riot-make-to-just`.

## Erwartete Ausgaben des `taxonomy-evidence`-Agenten

| Datei | Inhalt |
|---|---|
| `taxonomy-proof.md` | Hauptdossier: Taxonomie, Methode, Theorie, Empirie, Reliabilität, Falsifikation, Validitätsbedrohungen, Urteil |
| `target-evidence.csv` | Eine Zeile pro Target: D1-Kontext, D2-Artefakt, D3-Build, Gruppe, Präzedenzregel, Evidenz, Quellzeile, Konfidenz |
| `bibliography.bib` | Nur verifizierte BibTeX-Einträge |
| `reproduction.md` | Exakte Kommandos, Umgebung, Commit-SHA, beobachtete Ausgabe |
| `literature-search.md` | Datenbanken, Queries, Daten, Trefferzahlen, Ein-/Ausschluss, Snowballing |

Bereits vorhanden:

- `migration-scope.md` — generierte 71er-Liste nach Wellen.
- `decision-log.md` — Entscheidungsprotokoll 2.314 vs. 323 vs. 71.

## Aufruf

In einer Claude-Code-Session in `RIOT_Test` (oder weiterhin in OpenCode, dort mit `.opencode/research/`):

```text
Nutze den taxonomy-evidence-Agenten, um die 1/2A/2B/2C/3-Klassifikation der
323 benannten RIOT-Make-Targets zu validieren. Schreibe das Dossier auf
Deutsch und verifiziere jede DOI.
```

In Claude Code: `@taxonomy-evidence` erwähnen oder `claude --agent taxonomy-evidence` starten.

Weitere Ausgaben in diesem Ordner (Claude-Agenten):

- `config-analysis.md` — `config-analyst`
- `test-logs/` — `tester`

Konzept, Tool-Evaluation und Roadmap liegen im Thesis-Repo unter
`docs/05-migration-concept/`.

## Abgrenzung

Eine Taxonomie wird **validiert**, nicht deduktiv bewiesen. Das Dossier muss
kennzeichnen, welche Aussage `[source]`, `[observation]` oder `[inference]`
ist. Gegenbelege und ungelöste Konflikte gehören ins Dossier, nicht unter den
Tisch.
