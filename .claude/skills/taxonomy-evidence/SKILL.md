---
name: taxonomy-evidence
description: Validate the RIOT build-target taxonomy (1 / 2A / 2B / 2C / 3) with peer-reviewed literature, standards, and reproducible empirical checks. Use when asked to prove, justify, falsify, or document why a target belongs to a category.
---

# Taxonomy Evidence

Build an evidence dossier that answers one question:

> Is the RIOT build-target classification (Tier 1, 2A, 2B, 2C, Tier 3)
> exhaustive, mutually exclusive, theoretically grounded, and empirically
> valid for the 323 named targets in the corrected inventory?

This is a **validation**, not a mathematical proof. A taxonomy is justified by
construct validity, coverage, reliability, and falsification attempts. State
that explicitly in every deliverable.

### Inventory layers — do not mix them

| Layer | Count | Role |
|---|---:|---|
| Target declarations | 2.314 | Every literal declaration found by the scan; includes 1.991 internal/unnamed targets. Reference only. |
| Named targets | 323 | The classification universe. Groups: `1/2A/2B/2C/3 = 57/52/44/12/158`. |
| Canonical decision set | 87 | Subset from the app `help` context; `6/27/20/4/30`. Used for the fine-grained reliability sample. |
| Migration candidates | 71 | 44 `MIGRATE` + 27 `BRIDGE`; orthogonal to the group. |

The 87 are a subset, not the universe: `87 canonical + 215 additional + 21 net
new = 323`. Migrating and classifying are different questions: group describes
coupling, disposition describes command ownership.

## 1. The taxonomy under test

The unit of analysis is a **Make target invocation** (`make <target>` in a
resolved RIOT application context), not a source file and not a target name in
isolation. Classify the 323 named targets; use the 87 canonical targets for the
stratified reliability sample.

Define **operational coupling** as the set of preconditions that must hold
before the target can produce its intended effect:

| Dimension | Question |
|---|---|
| **D1 — Context** | Does the result depend on the resolved Make/Kconfig context (`BOARD`, `CPU`, `APPLICATION`, `USEMODULE`, `USEPKG`, `FEATURES_*`, toolchain selection)? |
| **D2 — Artifact/runtime** | Does it require a pre-existing firmware artifact (ELF, BIN, HEX, `.o`, MAP, profiling output) or live runtime/device state (terminal, flasher, port, debugger)? |
| **D3 — Build** | Does it initiate compilation, linking, compiler-backed analysis, firmware image construction, or a build/test workflow with a build prerequisite? |

Groups and decision rules:

| Group | Definition | Predicate | Examples (canonical 87 subset) |
|---|---|---|---|
| **1 — Stateless / No Build** | Repository- or host-only; no app/board context and no firmware artifact dependency. Documentation generation counts here because it is not firmware compilation. | `not D1 and not D2 and not D3` | `doc`, `doc-latex`, `doc-man`, `info-boards`, `info-emulated-boards`, `list-ttys` |
| **2A — Context-dependent** | Needs the fully resolved context to compute its answer; starts no compilation/linking and needs no build artifact. | `D1 and not D2 and not D3` | `help`, `info-*`, `check-toolchain-supported`, `compile-commands`, `cargo-preflight`, `pkg-prepare`, `reset`, `usb_id_check`, `test-on-ci-enabled`, `prepare_check_bindist`, `dependency-debug*`, `eclipsesym` |
| **2B — Artifact/runtime-dependent** | Reads, runs, flashes, or debugs an existing artifact or live target state; does not initiate the firmware build. | `D2 and not D3` | `debug*`, `term*`, `eval-*`, `info-buildsize`, `info-objsize`, `objdump`, `flash-only`, `preflash`, `fuzz`, `test-murdock` |
| **2C — Artifact lifecycle** | Manages or deletes build/package artifacts; needs resolved paths, but performs no compilation/linking. | `D2-lifecycle and not D3` | `clean`, `clean-intermediates`, `clean-pkg`, `distclean` |
| **3 — Build Required** | Initiates compilation/linking, compiler-backed analysis, firmware image construction, or a build/test workflow with a build prerequisite. Host-tool compilation also counts. | `D3` | `all`, `link`, `flash`, `elffile`, `hexfile`, `binfile`, `lstfile`, `flashfile`, `print-size`, `cosy`, `test-input-hash*`, `generate-Makefile.ci`, `mosquitto_rsmb`, … |

### Precedence rules (needed for mutual exclusivity)

Apply in order; the first matching rule wins:

1. **2C over 2B** when the primary effect is deletion/management rather than
   consumption of an artifact.
2. **3 over 2A/2B** when the recipe, a prerequisite, or a recursive `$(MAKE)`
   starts a compiler, linker, or compiler-backed analyzer.
3. **2B over 2A** when a pre-existing artifact or live device state is required.
4. **2A over 1** when output or exit status depends on the resolved context.
5. **1 only** if none of the above applies.

Any target that still satisfies two groups after precedence is a **taxonomy
defect**; report it instead of hiding it.

### Group counts and dispositions

| Group | 323 named | 87 canonical |
|---|---:|---:|
| 1 | 57 | 6 |
| 2A | 52 | 27 |
| 2B | 44 | 20 |
| 2C | 12 | 4 |
| 3 | 158 | 30 |
| **Total** | **323** | **87** |

Dispositions are a separate axis: `MIGRATE` 44, `BRIDGE` 27,
`OUT OF SCOPE` 252, `N/A` 1.991. A group-3 orchestration wrapper such as
`generate-Makefile.ci` can be `MIGRATE`; a group-2A target can be `BRIDGE`.
Never derive one from the other.

The authoritative per-target list is the `Migration Candidates` sheet of
`riot_all_make_targets.xlsx`; an extracted copy lives in
`.claude/research/migration-scope.md`.

## 2. Proof obligations

| ID | Obligation | How to discharge it | Artifact |
|---|---|---|---|
| **O1** | **Exhaustiveness** — every target in the inventory is assigned. | Recompute the 323 named targets from the workbook and compare sets; also check the 87 canonical subset. Assert no missing/extra. | `target-evidence.csv` |
| **O2** | **Mutual exclusivity** — no target is in two groups after precedence. | Re-run the predicates on every row; list conflicts. | `target-evidence.csv` |
| **O3** | **Construct validity** — each group's label matches observable behavior. | `make -pRrq`, `make -n <target>`, exit codes, clean vs. built state. | `reproduction.md` |
| **O4** | **Theoretical grounding** — categories are not ad hoc. | Map definitions to build-system theory and taxonomy-development literature. | dossier §Theory |
| **O5** | **Reliability** — independent coding agrees. | Two raters code all 87 canonical targets (or a stratified sample of the 323); report Cohen's κ. Target κ ≥ 0.80. | dossier §Reliability |
| **O6** | **Falsifiability** — each claim names an observation that would refute it. | Write the refuting observation before collecting evidence. | dossier §Falsification |

Additional checks:

- **Content validity:** do the five groups cover the conceptual space of build
  tooling responsibilities (inspection, configuration, artifact use, artifact
  lifecycle, synthesis)?
- **Criterion validity:** compare group membership with an independent signal,
  e.g. whether `make -n <target>` emits compiler/linker commands.
- **Ecological validity:** repeat on more than one board/app (native64,
  iotlab-m3, samr21-xpro, xipfs) and on the root Makefile.

## 3. Empirical protocol

Run everything from a **clean** RIOT checkout and record exact commands,
outputs, and commit SHA. Never trust the matrix alone. Use
`/home/mohammadjavad/Documents/RIOT` (master) for `make` observations; a
migration branch may already forward targets to `just`.

```sh
# Inventory for one concrete context
make -C examples/basic/hello-world BOARD=native64 help | sort -u

# Full Make database: targets, prerequisites, recipes
make -C examples/basic/hello-world BOARD=native64 -pRrq : 2>/dev/null > /tmp/db.txt

# Dry run: does the target compile or link?
make -C examples/basic/hello-world BOARD=native64 -n <target>

# Context sensitivity of help
make -C examples/basic/hello-world BOARD=iotlab-m3 help | sort -u
make -C examples/advanced/xipfs/xipfs_minimal_example BOARD=native64 help | sort -u

# Artifact dependence: classify with and without a built ELF
make -C examples/basic/hello-world BOARD=native64 clean
make -C examples/basic/hello-world BOARD=native64 -n info-buildsize
make -C examples/basic/hello-world BOARD=native64 all
make -C examples/basic/hello-world BOARD=native64 -n info-buildsize
```

Mechanical checks are bundled with this skill:

```sh
# O1/O2/counts of the 87-target corrected matrix (6/27/20/4/30)
python3 .claude/skills/taxonomy-evidence/verify_taxonomy.py \
  "/home/mohammadjavad/Documents/RIOT/riot_build_targets_matrix_corrected.xlsx"

# O1/O2/counts and dispositions of the 323-target inventory
python3 .claude/skills/taxonomy-evidence/verify_taxonomy.py --inventory \
  "/home/mohammadjavad/Documents/RIOT_Test/riot_all_make_targets.xlsx"

# Additionally compare the canonical inventory with a real help run
python3 .claude/skills/taxonomy-evidence/verify_taxonomy.py \
  --repo /home/mohammadjavad/Documents/RIOT \
  --help-context examples/basic/hello-world --board native64

# Legacy tier-only reference workbook (expected 7 / 59 / 21), if present
python3 .claude/skills/taxonomy-evidence/verify_taxonomy.py --reference \
  "<path-to-legacy-reference.xlsx>"
```

**Important:** the checkout at `RIOT_Forked` is a migration branch. Its `help`
target may call `just`, which need not be installed. Use
`/home/mohammadjavad/Documents/RIOT` (clean `master`) for all `make`-based
observations, and state which checkout and commit each observation came from.

Rules of evidence:

1. A target is **D3** if `make -n` shows a compiler, linker, assembler, or
   compiler-backed analyzer being invoked (directly or through a prerequisite).
   `$(MAKE) -pRrq` and `make -q` do **not** count.
2. A target is **D2** if it fails, or produces meaningless output, without a
   pre-existing artifact or live device state.
3. A target is **D1** if its output or exit code changes with `BOARD`, `APP`,
   `USEMODULE`, `USEPKG`, or toolchain while no build occurs.
4. Documentation generation is **not** D3: D3 is the firmware/build graph, not
   any file-producing host tool. Record this as an explicit scope decision.
5. Prefer the target's own recipe and prerequisites over its name.

## 4. Literature search protocol

### Sources, in evidence hierarchy

1. Peer-reviewed journals and conferences (ACM DL, IEEE Xplore, SpringerLink,
   ScienceDirect, Scopus, Web of Science).
2. Standards (ISO/IEC/IEEE, POSIX, GNU manuals).
3. Official project documentation and source code.
4. Technical reports and theses.
5. Practitioner blogs only for context, never as proof.

### Query strings

Use Boolean operators and record the exact query, database, date, and hits:

```text
("build system" OR "build systems") AND (taxonomy OR classification OR categorization)
("build target" OR "build targets") AND (dependency OR artifact OR incremental)
("GNU Make" OR "makefile") AND (semantics OR "recursive make")
("software taxonomy" OR "typology") AND (development OR validation OR evaluation)
("empirical software engineering") AND ("case study" OR validity OR reliability)
("reproducible builds") AND (artifacts OR integrity)
("build maintenance") AND (effort OR evolution)
("configuration variability" OR "feature model") AND (build)
```

### Inclusion / exclusion

Include: peer-reviewed or standards documents; explicit method or theory;
build systems, Make, software taxonomy, empirical SE, reproducibility,
configuration. Exclude: unverifiable, marketing, no method, non-software
analogy without transfer argument.

### Snowballing

For each included paper, scan (a) its references and (b) papers citing it.
Stop when two consecutive rounds add no new concept.

### Citation verification

**Never invent a citation.** For every entry:

```sh
curl -s "https://api.crossref.org/works/<DOI>"
```

Confirm title, authors, year, venue, volume, pages. If a DOI does not resolve,
mark the entry `UNVERIFIED` and do not use it as proof. Preprints must be
labelled as preprints.

## 5. Seed bibliography

Start here, then extend. All DOIs below were verified against Crossref.

- Mokhov, Mitchell, Peyton Jones (2018). *Build systems à la carte.* PACMPL
  2(ICFP), 1–29. DOI `10.1145/3236774`.
- Mokhov, Mitchell, Peyton Jones (2020). *Build systems à la carte: Theory and
  practice.* JFP 30. DOI `10.1017/S0956796820000088`.
- Feldman (1979). *Make — a program for maintaining computer programs.*
  Software: Practice and Experience 9(4), 255–265. DOI `10.1002/spe.4380090402`.
- Miller (1998). *Recursive Make Considered Harmful.* AUUGN 19(1), 14–25.
  No DOI; verify the AUUG archive URL.
- Nickerson, Varshney, Muntermann (2013). *A method for taxonomy development
  and its application in information systems.* EJIS 22(3), 336–359.
  DOI `10.1057/ejis.2012.26`.
- Doty & Glick (1994). *Typologies as a unique form of theory building.*
  AMR 19(2), 230–251. DOI `10.2307/258704`.
- Runeson & Höst (2009). *Guidelines for conducting and reporting case study
  research in software engineering.* EMSE 14(2), 131–164.
  DOI `10.1007/s10664-008-9102-8`.
- McIntosh, Adams, Nguyen, Kamei, Hassan (2011). *An empirical study of build
  maintenance effort.* ICSE 2011, 141–150. DOI `10.1145/1985793.1985813`.
- Lamb & Zacchiroli (2022). *Reproducible builds: increasing the integrity of
  software supply chains.* IEEE Software 39(2), 62–70.
  DOI `10.1109/MS.2021.3073045`.
- Cohen (1960). *A coefficient of agreement for nominal scales.* EPM 20(1),
  37–46. DOI `10.1177/001316446002000104`.
- Landis & Koch (1977). *The measurement of observer agreement for categorical
  data.* Biometrics 33(1), 159–174. DOI `10.2307/2529310`.
- GNU Project. *GNU Make Manual.* <https://www.gnu.org/software/make/manual/>
- ISO/IEC/IEEE 42010:2022, *Software, systems and enterprise — Architecture
  description.*
- ISO/IEC 25010:2023, *Systems and software Quality Requirements and Evaluation
  (SQuaRE) — Product quality model.*

## 6. Deliverables

Write only inside `.claude/research/` (or the output directory the user
names). Recommended files:

```text
.claude/research/
├── taxonomy-proof.md        # main dossier, in the user's language
├── target-evidence.csv      # one row per named target: D1/D2/D3, group, disposition, evidence
├── bibliography.bib         # verified BibTeX entries
├── reproduction.md          # exact commands, environment, commit SHA, outputs
└── literature-search.md     # queries, databases, hit counts, inclusion decisions
```

### `taxonomy-proof.md` structure

```markdown
# Validation of the RIOT Build-Target Taxonomy

## 0. Scope and disclaimer
What is and is not proven. Unit of analysis. Commit SHA.

## 1. Taxonomy and decision rules
Definitions, predicates, precedence.

## 2. Method
Case-study design (Runeson & Höst), data collection, coding procedure,
reliability procedure, literature search.

## 3. Theoretical grounding
For each group: which theory or standard supports the distinction, with
citation and the exact claim it supports. Separate source claim from inference.

## 4. Empirical results
O1–O6 with tables and command evidence.

## 5. Reliability
Rater procedure, agreement matrix, Cohen's κ, disagreements and resolution.

## 6. Falsification attempts
Observations that would have refuted each group; what was observed.

## 7. Threats to validity
Construct, internal, external, conclusion validity; mitigations.

## 8. Verdict
Per group: supported / partially supported / not supported. Overall:
the taxonomy is a validated engineering classification, not a proof.

## 9. Open issues and counter-evidence
Anything that does not fit, including alternative taxonomies.

## References
Verified entries only.
```

### `target-evidence.csv`

One row per named target (323), with the 87 canonical targets flagged. The
`disposition` column is independent of `group`.

```csv
target,group,disposition,D1_context,D2_artifact,D3_build,precedence_rule,observable_evidence,source_location,confidence
help,2A,MIGRATE,true,false,false,4,"help output: native64 87 vs iotlab-m3 77 targets","Makefile.include:1000-1001",high
info-build,2A,BRIDGE,true,false,false,4,"needs resolved BOARD/CPU/module state; no compile","makefiles/info.inc.mk:33",high
```

## 7. Pitfalls that invalidate the result

- **Name-based classification.** `flashfile` sounds like flashing but is a build
  product; `fuzz` sounds like testing but only runs an existing binary.
- **Confusing “no compilation” with “stateless”.** `help` runs
  `$(MAKE) -pRrq` and evaluates the whole context.
- **Treating documentation artifacts as firmware builds.** `doc` produces HTML,
  but not a firmware image; state the scope decision.
- **Counting `help` output as the complete target universe.** It is one
  context's user-facing filter, not all Make targets.
- **Ignoring recursive `$(MAKE)`.** A recipe that calls another make target may
  trigger a build indirectly.
- **Cherry-picking literature.** Report sources that support *and* sources that
  challenge the taxonomy.
- **Claiming proof.** A taxonomy is validated by evidence and use, not proven
  deductively from definitions.

## 8. Reporting rules

- Cite every theoretical claim with author, year, and page/section.
- Mark each statement as `[source]`, `[observation]`, or `[inference]`.
- Give exact file:line evidence for RIOT claims.
- Report negative results and unresolved conflicts.
- Never modify the RIOT source tree, the thesis, or the matrix while auditing.
- Never commit or push.

## Vorgaben Termin 2026-11-13 (D22)

- Reproducibility is mandatory: a deterministic rule script that recomputes
  the groups and reports differences to the workbook; same input → same
  output (fixed RIOT commit, sorted output, logged versions).
- New targets must be classified automatically (inventory diff + rules) or
  rejected in CI with a message.
- Ecological validity now uses the board **nRF52840** (plus `native64` as
  contrast); record hardware dependency as an attribute.
