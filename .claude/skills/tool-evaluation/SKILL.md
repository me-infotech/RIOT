---
name: tool-evaluation
description: Protocol for a scientifically defensible tool selection in the RIOT Make migration — requirements-derived criteria, DESMET feature analysis, AHP weights with consistency ratio, weighted scoring, sensitivity analysis, hands-on screening, and verified sources. Use when evaluating, re-scoring or defending a tool choice for the task, configuration, or build layer.
---

# Tool Evaluation Protocol

Baseline document (extend, do not duplicate):
`/home/mohammadjavad/Documents/riot-build-config-thesis/docs/05-migration-concept/tool-evaluation.md`
Verified bibliography: `.../05-migration-concept/references.bib`.

## Method (cite these, all DOIs verified 2026-11-12)

| Step | Method | Source |
|---|---|---|
| Frame | Design Science (artefact = migration concept) | Hevner et al. 2004, doi:10.2307/25148625 |
| Evaluate tools | DESMET *feature analysis* (screening + hands-on) | Kitchenham et al. 1997, doi:10.1049/cce:19970304 |
| Weight criteria | AHP pairwise comparison, consistency ratio CR < 0.10 | Saaty 1990, doi:10.1016/0377-2217(90)90057-I |
| Gray literature | multivocal review rules (docs, release notes, forums) | Garousi et al. 2019, doi:10.1016/j.infsof.2018.09.006 |
| Case evidence | case-study reporting for RIOT experiments | Runeson & Höst 2009, doi:10.1007/s10664-008-9102-8 |
| Quality vocabulary | ISO/IEC 25010 characteristics | standard (cite edition used) |

## Procedure

1. **Layer.** Fix the layer: task (T), configuration (C), or build (B).
   Never score a tool on another layer's criteria.
2. **Requirements → criteria.** Each criterion `K-xx` traces to a requirement
   `R-xx`, which traces to the research question, a meeting decision, or an
   `[observation]` in RIOT (`file:line`). Mark criteria as *mandatory* (K.O.)
   or *weighted*.
3. **Candidate set.** Document inclusion/exclusion: active maintenance (release
   in last 12 months), OSI license, Linux support, documented, relevant to the
   layer. Always include the **status quo (GNU Make)** as baseline.
4. **Screening (K.O.).** Remove candidates failing a mandatory criterion;
   record why.
5. **Weights.** Pairwise comparisons on Saaty's 1–9 scale; compute the
   principal eigenvector and CR with a script (`numpy` absent → power
   iteration in plain Python). CR ≥ 0.10 → revise judgements.
   Ideally obtain judgements from ≥2 people (author + supervisor) and report
   both.
6. **Scoring.** Ordinal 0–3 per criterion
   (0 = not supported, 1 = workaround, 2 = supported, 3 = supported natively
   and documented). Every score: one-line justification + evidence pointer
   (URL + access date, release tag, `file:line`, experiment log).
7. **Hands-on.** For the top 2–3 per layer, run the same RIOT pilot
   (`info-boards`, `info-modules`, `clean` for T; config round-trip for C;
   `hello-world` for `native64` for B) and log commands, versions, timings
   (≥10 runs, median + IQR).
8. **Aggregate.** Weighted sum with a script; publish the script and inputs.
9. **Sensitivity.** Vary each weight ±20 % (renormalise) and report rank
   reversals; also report the ranking with equal weights.
10. **Threats to validity.** Construct (criteria choice), internal (single
    rater, author bias), external (one RIOT revision, one host), reliability
    (second rater, Cohen's κ on scores).

## Evidence rules

- Verify DOIs: `curl -s https://api.crossref.org/works/<doi>`.
- Tool facts from official docs or release pages, with access date. Popularity
  numbers (GitHub stars) are context only, never a criterion on their own.
- Label `[source]`, `[observation]`, `[inference]`.
- No hands-on result → score marked `doc-only`.

## Output

Update `tool-evaluation.md` sections: requirements, criteria, candidates,
screening, weights (with CR), score matrix (with evidence), results,
sensitivity, recommendation per layer, threats, open points.
Answer in German. Never commit.

## Vorgaben Termin 2026-11-13 (D22)

- Scope of the comparison: **2–3 tools**, chosen from what is widely used;
  the choice is justified.
- Examples: **2–3 targets per category**, selection justified in writing.
- Hands-on runs on **nRF52840** (Docker build allowed); state every
  limitation with its reason.
