#!/usr/bin/env python3
"""Mechanical checks for the RIOT build-target taxonomy.

No third-party dependencies: reads .xlsx directly (zipfile + ElementTree).

Checks:
  O1  every target appears exactly once
  O2  every target has exactly one group and the tier matches the group
  O3  optional: compare the workbook inventory with `make help` for a context

Usage:
  python3 verify_taxonomy.py [WORKBOOK]
  python3 verify_taxonomy.py --inventory [INVENTORY_WORKBOOK]
  python3 verify_taxonomy.py --help-context examples/basic/hello-world --board native64
  python3 verify_taxonomy.py --reference   # check a tier-only reference workbook
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

TIER_OF_GROUP = {"1": "1", "2A": "2", "2B": "2", "2C": "2", "3": "3"}
EXPECTED_GROUPS = {"1": 6, "2A": 27, "2B": 20, "2C": 4, "3": 30}
EXPECTED_TOTAL = 87

# Full named-target inventory (riot_all_make_targets.xlsx, sheet "Named Targets")
INVENTORY_SHEET = "Named Targets"
INVENTORY_GROUPS = {"1": 57, "2A": 52, "2B": 44, "2C": 12, "3": 158}
INVENTORY_TOTAL = 323
INVENTORY_DISPOSITIONS = {"MIGRATE": 44, "BRIDGE": 27, "OUT OF SCOPE": 252}
INVENTORY_DISPOSITION_TOTAL = 323
INVENTORY_DEFAULT = (
    "/home/mohammadjavad/Documents/RIOT_Test/riot_all_make_targets.xlsx"
)


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"([A-Z]+)", ref).group(1):
        n = n * 26 + ord(ch) - 64
    return n


def _sheet_path(z: zipfile.ZipFile, wanted: str = "Target Matrix") -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {
        r.attrib["Id"]: r.attrib["Target"]
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall(
            PKG_REL_NS + "Relationship"
        )
    }
    sheets = wb.find(NS + "sheets")
    for sheet in sheets:
        if sheet.attrib.get("name") == wanted:
            return "xl/" + rels[sheet.attrib[REL_NS + "id"]]
    return "xl/" + rels[sheets[0].attrib[REL_NS + "id"]]


def read_rows(path: str, sheet: str = "Target Matrix") -> list[dict[int, str]]:
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = [
            "".join(t.text or "" for t in si.iter(NS + "t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(
                NS + "si"
            )
        ]
    sheet_xml = ET.fromstring(z.read(_sheet_path(z, sheet)))
    rows: list[dict[int, str]] = []
    for row in sheet_xml.iter(NS + "row"):
        cells: dict[int, str] = {}
        for c in row.findall(NS + "c"):
            ref = _col(c.attrib["r"])
            t = c.attrib.get("t")
            v = c.find(NS + "v")
            inline = c.find(NS + "is")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr" and inline is not None:
                val = "".join(x.text or "" for x in inline.iter(NS + "t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            if val:
                cells[ref] = val
        if cells:
            rows.append(cells)
    return rows


def extract(rows: list[dict[int, str]], reference: bool) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows[1:]:  # skip header
        target = row.get(3)
        if not target:
            continue
        tier = (row.get(1) or "").strip()
        raw_group = (row.get(2) or "").strip()
        if reference or raw_group not in TIER_OF_GROUP:
            group = tier
        else:
            group = raw_group
        out.append({"tier": tier, "group": group, "target": target})
    return out


def check(entries: list[dict[str, str]], reference: bool) -> int:
    failures = 0
    names = [e["target"] for e in entries]
    counts = collections.Counter(e["group"] for e in entries)

    print(f"targets: {len(names)} (unique: {len(set(names))})")
    print("groups:", dict(counts))

    if len(names) != len(set(names)):
        print("O1 FAIL duplicate targets")
        failures += 1
    else:
        print("O1 PASS every target appears exactly once")

    bad = [
        e
        for e in entries
        if e["group"] in TIER_OF_GROUP
        and e["tier"] != TIER_OF_GROUP[e["group"]]
    ]
    if bad:
        print("O2 FAIL tier/group mismatch:", bad[:10])
        failures += 1
    else:
        print("O2 PASS every target has one group and a consistent tier")

    if reference:
        expected = {"1": 7, "2": 59, "3": 21}
        label = "reference baseline"
    else:
        expected = EXPECTED_GROUPS
        label = "corrected matrix"
    if dict(counts) != expected or len(names) != EXPECTED_TOTAL:
        print(f"COUNT FAIL {label} expected {expected} / {EXPECTED_TOTAL}, got {dict(counts)} / {len(names)}")
        failures += 1
    else:
        print(f"COUNT PASS {label}: {expected} = {EXPECTED_TOTAL}")
    return failures


def extract_inventory(rows: list[dict[int, str]]) -> list[dict[str, str]]:
    """Extract the 323 named targets from the 'Named Targets' sheet.

    Layout: A=group, B=tier, C=target, D=scope, E=disposition.
    """
    out: list[dict[str, str]] = []
    for row in rows[1:]:  # skip header
        target = (row.get(3) or "").strip()
        if not target:
            continue
        out.append(
            {
                "group": (row.get(1) or "").strip(),
                "target": target,
                "disposition": (row.get(5) or "").strip(),
            }
        )
    return out


def check_inventory(entries: list[dict[str, str]]) -> int:
    failures = 0
    names = [e["target"] for e in entries]
    groups = collections.Counter(e["group"] for e in entries)
    dispositions = collections.Counter(e["disposition"] for e in entries)

    print(f"named targets: {len(names)} (unique: {len(set(names))})")
    print("groups:", dict(groups))
    print("dispositions:", dict(dispositions))

    if len(names) != len(set(names)):
        print("INV-O1 FAIL duplicate targets")
        failures += 1
    else:
        print("INV-O1 PASS every named target appears exactly once")

    unknown = sorted(set(groups) - set(INVENTORY_GROUPS))
    if unknown:
        print("INV-O2 FAIL unknown groups:", unknown)
        failures += 1
    else:
        print("INV-O2 PASS every target has a known group")

    if dict(groups) != INVENTORY_GROUPS or len(names) != INVENTORY_TOTAL:
        print(
            "INV-COUNT FAIL expected "
            f"{INVENTORY_GROUPS} / {INVENTORY_TOTAL}, got {dict(groups)} / {len(names)}"
        )
        failures += 1
    else:
        print(f"INV-COUNT PASS groups {INVENTORY_GROUPS} = {INVENTORY_TOTAL}")

    if (
        dict(dispositions) != INVENTORY_DISPOSITIONS
        or sum(dispositions.values()) != INVENTORY_DISPOSITION_TOTAL
    ):
        print(
            "INV-DISP FAIL expected "
            f"{INVENTORY_DISPOSITIONS} / {INVENTORY_DISPOSITION_TOTAL}, "
            f"got {dict(dispositions)} / {sum(dispositions.values())}"
        )
        failures += 1
    else:
        print(
            f"INV-DISP PASS {INVENTORY_DISPOSITIONS} = {INVENTORY_DISPOSITION_TOTAL}"
        )
    return failures


def help_targets(repo: str, app: str, board: str) -> set[str] | None:
    proc = subprocess.run(
        ["make", "-C", app, f"BOARD={board}", "help"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        print(f"\nCONTEXT ERROR: make help failed in {repo}/{app} (exit {proc.returncode})")
        print(proc.stderr.strip()[:2000])
        return None
    return {
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip() and not line.startswith("make:")
    }


def compare_help(entries: list[dict[str, str]], repo: str, app: str, board: str) -> int:
    expected = {e["target"] for e in entries}
    actual = help_targets(repo, app, board)
    if actual is None:
        return 1
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    print(f"\nhelp context: {repo}/{app} BOARD={board} -> {len(actual)} targets")
    if missing:
        print("in workbook, not in help:", missing)
    if extra:
        print("in help, not in workbook:", extra)
    if missing or extra:
        print("CONTEXT FAIL inventory mismatch")
        return 1
    print("CONTEXT PASS inventory matches")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workbook",
        nargs="?",
        default=None,
        help="workbook to check; defaults to the corrected 87-target matrix",
    )
    parser.add_argument("--reference", action="store_true", help="expect 7/59/21")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="check the full named-target inventory (323, sheet 'Named Targets')",
    )
    parser.add_argument("--help-context", help="application directory to compare")
    parser.add_argument("--board", default="native64")
    parser.add_argument(
        "--repo",
        default="/home/mohammadjavad/Documents/RIOT",
        help="clean RIOT checkout used for empirical checks",
    )
    args = parser.parse_args()

    if args.inventory:
        workbook = args.workbook or INVENTORY_DEFAULT
        entries = extract_inventory(read_rows(workbook, INVENTORY_SHEET))
        return 1 if check_inventory(entries) else 0

    workbook = (
        args.workbook
        or "/home/mohammadjavad/Documents/RIOT/riot_build_targets_matrix_corrected.xlsx"
    )
    entries = extract(read_rows(workbook), args.reference)
    failures = check(entries, args.reference)
    if args.help_context:
        failures += compare_help(
            entries, args.repo, args.help_context, args.board
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
