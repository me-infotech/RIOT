# Test log 2026-11-14 — task layer hands-on: GNU Make vs. just vs. Task (D24)

Examples (D24): `doc`, `generate-features`, `list-ttys` (group 1).
Tools: GNU Make 4.3 (host) / 4.4.1 (riotbuild image), just 1.59.0,
Task 3.54.0 (`riot-build-config-thesis/experiments/task-layer/Taskfile.yml`,
port of the just recipes of `RIOT_Test` @`3857b24970`).
Trees: clones in the scratchpad with paths of equal length, `ref` = RIOT
`0be9299ca9` (Make targets), `cur` = `RIOT_Test` `3857b24970` (just recipes,
Taskfile copied into the root). Where both trees are needed for the same
input, the justfile, `just/` and the Taskfile were copied into `ref`.

## Parity

| Example | Cases | Result |
|---|---|---|
| `list-ttys` | 9 QUIET/Q cases (default; `QUIET` env 0/empty/1; `QUIET=0` on the command line; `Q` env empty; `Q=`/`Q=@` on the command line; `QUIET=0 Q=@`); Make in the app context, just/Task in the root; stdout + exit status, checkout path normalised | **identical in all 9 cases** for Make, just and Task; stderr differs only by Make's board-alias note (`using BOARD="native64" as "native"`, app context) |
| `generate-features` | regenerate `makefiles/features_existing.inc.mk` in the same tree (`ref`) | **byte-identical** for Make, just and Task (SHA-256 `824d9987…`), equal to the committed file |
| `doc` | full Doxygen HTML in the riotbuild image (Doxygen 1.15.0, Graphviz 14.1.2), same tree and mount path `/riot` | all three exit 0, **30,915 files each; 30,914 byte-identical**, only `html/doxygen.css` differs (Doxygen writes the generation time into it, see below); Doxygen warnings on stderr identical → **parity** |

`doxygen.css`: two identical `task doc` runs in a full (not `--shared`)
clone differ in exactly this file, lines 2071/2073
(`--datetime: 'Sat Nov 14 2026 11:38:15'` vs. `11:41:43`, `--time`).
Doxygen writes the generation time into the stylesheet; the difference is
not caused by the task runner. The full clone run had no `git` errors.

Side finding (environment): in the `--shared` clone, Make's `doc` printed 48
extra `git` errors inside the container (`unable to normalize alternate
object path`, the alternates file points to a host path); Make evaluates
`$(shell git ls-tree …)` more often than just/Task run it once. The HTML was
not affected.

## Behaviour and usability (checked by running the commands)

| Aspect | GNU Make | just | Task |
|---|---|---|---|
| list commands with description | no root `help` (`make help` → `unrecognized target`); app `help` lists names only | `just --list`, descriptions and groups | `task --list`, descriptions (`desc`) |
| dry run | `make -n` prints the recipe | `just --dry-run` prints the recipe, also for `@` lines | `task --dry` prints **nothing** for tasks with `silent: true`; to see the command the task must not be silent |
| unknown name | exit 2, `*** … Error 1` after the welcome text | exit 1, `error: justfile does not contain recipe` | exit 200, `task: Task "nosuch" does not exist` |
| settings like `?=` (env set, even empty, wins; command line wins over env) | native | `env("X", default)` + `just X=value` | `sh: echo "${X-default}"` dynamic variables + `task X=value` |
| shell of the recipe lines | `/bin/sh` | `/bin/sh` (`set shell`), shebang recipes | built-in Go interpreter (`mvdan.cc/sh`, `$0` = `gosh`), not the system shell |
| up-to-date check (e.g. `src/changelog.md`) | native file rules | none: written by hand (`-nt` test in the recipe) | `sources`/`generates` available (not used in the port, to keep behaviour equal) |
| availability | everywhere (also riotbuild) | Ubuntu 24.04 package (1.21.0, older than tested 1.59.0); not in riotbuild | not packaged in Ubuntu; not in riotbuild; official static binary |
| file format | Makefile | justfile (own syntax) | YAML + Go templates |

## Timing

Host (Intel N150, otherwise idle), median of 20 runs after one warm-up,
output discarded (`timing.py` in the scratchpad):

| Command | Make | just | Task |
|---|---:|---:|---:|
| dry run `generate-features` (start-up + parse) | 91 ms | 14 ms | 199 ms |
| `generate-features` | 293 ms | 188 ms | 287 ms |
| `list-ttys` | 267 ms (app context) | 105 ms | 230 ms |
| list commands | 546 ms (`make help`, app) | 15 ms | 147 ms |

Task's start-up cost is the tool itself: `task --list` with a one-task
Taskfile (no variables) also takes 202 ms (median of 20). Make's cost comes
from parsing the root or application makefiles. Absolute values are small
for interactive use; they matter when a command runs often (CI loops).
`doc` wall time in the container (single run each, other load on the host
possible): Make 167 s, just 202 s, Task 155 s — one run each, not a
benchmark; Doxygen dominates.

## Reading [inference]

- Functional parity is reachable with both just and Task for the three
  examples; the decision between them rests on behaviour/usability and
  availability, not on output.
- Task's built-in shell and the silent/dry-run interaction are the main
  practical differences to Make's behaviour; just stays closer to Make
  (`/bin/sh`, `@`, dry run).
