# Test log 2026-11-14 — configuration layer on nrf52840dk: Make variables vs. riot-app.yaml (D24)

Examples (D24): `info-modules`, `info-features-used`, `info-cpu` (group 2A),
plus `info-build-json`. Compared: application settings as Make variables
(`ref` = RIOT `0be9299ca9`) and as `riot-app.yaml` + generated
`riot-app.inc.mk` (`cur` = `RIOT_Test` `c3c6c2d971`). Kconfig is not part of
the hands-on comparison (D24; only the AHP evaluation).
Full clones (not `--shared`) with paths of equal length in the scratchpad,
`BOARD=nrf52840dk`, GNU Make 4.3 (host), no toolchain needed (no build).

## 1. Parity of the resolved configuration (8 cases)

`make BOARD=nrf52840dk <target>` in both trees, stdout + stderr + exit
status, checkout path normalised:

| App | info-modules | info-features-used | info-cpu | info-build-json |
|---|---|---|---|---|
| hello-world | identical (62 lines) | identical (25) | identical (2) | identical (46) |
| gnrc_networking | identical (209) | identical (31) | identical (2) | identical (46) |

`info-build-json` reports `"BOARD": "nrf52840dk"`, `"CPU": "nrf52"`.

## 2. Precedence (25 cases)

The 25 cases of `2026-11-13-p4-config-layer.md` section 3 with
`nrf52840dk` instead of `native64`/`native` (environment vs. command line
for BOARD, DEVELHELP, QUIET, APPLICATION, RIOTBASE, CFLAGS, USEMODULE,
USE_ZEP, ZEP_PORT_BASE, EXTERNAL_BOARD_DIRS; 12 variables printed per
case): **identical, 327 lines**; BOARD resolves to `nrf52840dk` where it
is given. Precedence `?=`/`+=` therefore behaves the same on the hardware
board as on native.

## 3. Detection of typical configuration mistakes (hello-world)

Make side: the mistake in the app Makefile, `make info-debug-variable-*`.
YAML side: the mistake in `riot-app.yaml`, generator `riot_app_config.py`
(which also runs in CI via `check_riot_app_config_up_to_date.sh`).

| Mistake | Make variables | riot-app.yaml |
|---|---|---|
| typo in a name (`DEVELHLEP`) | **silent**: exit 0, `DEVELHELP` falls back to 0 | **rejected**: "Additional properties are not allowed ('develhlep' was unexpected)" |
| wrong type (`yes` for DEVELHELP) | **silent**: exit 0, `DEVELHELP=yes` (not `1`, so DEVELHELP is off) | **rejected**: YAML 1.1 boolean hint, with line number |
| number in another notation (`01`) | **silent**: `QUIET=01` | **rejected**: octal/hex/sexagesimal hint, with line number |
| required setting missing (RIOTBASE) | fails late: `No rule to make target '/Makefile.include'` | **rejected** early: "'riotbase' is a required property" |
| unknown board (`nrf52840dkx`) | fails at parse time: "The specified board nrf52840dkx does not exist" | generator accepts it (the schema does not list boards); make fails with the same message |
| setting given twice | **silent**: first `?=` wins | **rejected**: "duplicate key 'quiet' (line 25)" |

Counts: Make detects 2 of 6 (one late with an unclear message); the YAML
generator detects 5 of 6, the sixth (board name) is detected by Make in
both variants. Note: the first run of the board case passed `BOARD=` on
the command line, which hides the default; it was repeated without it.

## Reading [inference]

- The configuration layer changes where settings are written, not what
  Make resolves: on `nrf52840dk` the resolved state and the precedence are
  unchanged.
- The benefit of the declarative file is early, explained rejection of
  mistakes that Make accepts silently; the board list is not part of the
  schema (it would duplicate `boards/`; a check against the board
  directories belongs to the resolver, P6).

Evidence: `.claude/research/config-nrf52840dk/` (`prec_nrf.sh`,
`errors.sh`, `prec.ref.txt`, `prec.cur.txt`, `errors.txt`,
`info-parity.txt`, `SHA256SUMS`; scratchpad path replaced by `<SCRATCH>`).
