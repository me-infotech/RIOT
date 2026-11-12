---
name: migration-concept
description: Structure, patterns and quality rules for the thesis' migration concept of RIOT's GNU Make tooling — three layers (task, configuration, build), incremental migration that moves responsibility out of Make (just = group 1 only, no Make in just), phase gates, contracts, risks. Use when writing, extending or checking the concept or the roadmap.
---

# Migration Concept

The thesis delivers a **concept** ("wie man vorgeht"), validated by selected
proofs of concept in `RIOT_Test`. Place concept text in
`riot-build-config-thesis/docs/05-migration-concept/`.

## Core model

| Layer | Owns | Today | Target (concept) |
|---|---|---|---|
| Task | **group 1 only**: commands without Make context, artifacts, runtime, lifecycle or build (`info-boards`, `doc`, `welcome`, `generate-*`, `list-ttys`, …; list: `RIOT_Test/.claude/research/just-scope.md`) | Make targets | command runner (`just`) owns the full logic, never calls Make; the target is removed from Make and callers use just (D20) |
| Configuration | inputs (`BOARD`, `USEMODULE`, `DEVELHELP`, …) and resolved state (`CPU`, features, modules, `BINDIR`) | spread over app Makefile, env, `Makefile.local`, board/CPU `Makefile*`, `Makefile.dep`, Kconfig | one tool-independent input file + one resolved-state export; Make stays single resolver until the build layer moves |
| Build | groups 2A/2B/2C/3: context-dependent introspection (`info-modules`, `help`), artifact/runtime (`term`, `debug`, `info-buildsize`), artifact lifecycle (`clean`), build | GNU Make (`Makefile.include`, `Makefile.base`) | stays Make-native until the build tool takes over; target CMake + Ninja, compared hands-on with Meson + Ninja (PoC: one module + `hello-world`) |

**Main rule (user, 2026-11-12, D17):** the migration takes responsibility
**out of** Make. A just recipe that calls Make (`just → make _helper`) only
adds a surface on top of Make and is rejected as a pattern, even where the
workbook says `MIGRATE`/`BRIDGE`.

## Patterns (with verified sources)

- **Incremental migration with gateways** — legacy and new system coexist,
  a gateway translates calls (Bisbal et al. 1999, doi:10.1109/52.795108).
  In RIOT (D20) group-1 targets are extracted completely: no Make entry
  remains, callers switch to just; there is no path from just into Make.
- **Spiral/iterative migration phases; requirements gathering and community
  buy-in decide success** (Suvorov et al. 2012, doi:10.1109/ICSM.2012.6405267).
- **Build system model** — scheduler + rebuilder; a task runner has neither,
  so it must not own work that needs incremental rebuild (Mokhov et al. 2018,
  doi:10.1145/3236774).
- **Dynamic analysis for parity** — validate migrated scripts by comparing
  observed behaviour (Gligoric et al. 2014, doi:10.1145/2660193.2660239).
- **Build maintenance cost** — build code co-evolves with source and costs
  effort; technology choice matters (McIntosh et al. 2011/2015,
  doi:10.1145/1985793.1985813, doi:10.1007/s10664-014-9324-x).
- **Recursive Make problems** (Miller 1998; Mokhov et al. 2016,
  doi:10.1145/2976002.2976011) — relevant to `$(MAKE) -C` chains in RIOT.
- **Strangler Fig** (Fowler, gray literature) — only as illustration.

## Required sections of the concept

1. Ausgangslage (evidence: inventory 2.314/323, group 1 = 57, just scope 36+2, observations)
2. Ziele und Nicht-Ziele (incl. "GNU Make wird in dieser Arbeit nicht ersetzt")
3. Anforderungen (R-xx, traced)
4. Schichtenmodell und Verantwortlichkeiten
5. Entscheidungsregeln (taxonomy 1/2A/2B/2C/3 → layer; group 1 → just only if Make-free; incl. the rejected just → make pilot as counter-example)
6. Verträge: Auslagerungs-Vertrag (Target nur noch in just, Aufrufer umgestellt, zentrale Einstellungen), Konfigurations-Vertrag (input + resolved state),
   Paritäts-Vertrag (what "no behaviour change" means, incl. allowed deviations)
7. Werkzeugwahl je Schicht (link to tool evaluation)
8. Vorgehen in Phasen mit Gates (link to roadmap)
9. Verifikation und Metriken
10. Risiken, Gegenargumente (RIOT forum 2021), Rückfallstrategie
11. Übertragbarkeit (what generalises beyond RIOT)

## Quality rules

- Every requirement and design decision traces to evidence.
- A phase gate is binary and checkable (command/script + expected result).
- Rollback is "restore the Make rule and the callers from git" — keep it true.
- Check every proposed just recipe against `just-scope.md`; a Make call in just
  or a 2A/2B/2C/3 target in just is a concept violation.
- Never claim community acceptance; propose how to obtain it (RFC/forum post,
  maintainer review) as part of the roadmap.
- German text, English terms. Never commit.
