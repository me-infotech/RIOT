#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Dependency rules of a RIOT module in YAML (authoritative) and the
generated Makefile.dep (transitional Make adapter), decision D27.

  riot_deps.py export <Makefile.dep>…   one-time conversion: write the YAML
                                        next to each make file
  riot_deps.py generate [--check] [--all | <deps.yaml>…]
                                        write (or check) the Makefile.dep
                                        generated from each YAML
  riot_deps.py items <deps.yaml>        print the rules as the resolver's
                                        internal items (JSON)

File names: `Makefile.dep` <-> `deps.yaml`, `Makefile.<x>.dep` <->
`<x>.deps.yaml` in the same directory.

YAML format (schema_version 1): `rules:` is an ordered list; each entry is
one of
  add: {VAR: [words]}                 VAR += words
  assign: {var, op, value}            VAR op value (op: = := ?=)
  assign: {var, op, make_expr}        value is a Make expression (marked)
  include: [paths], optional: bool    (-)include, paths with $(VAR)
  include_make_expr: text             include with a Make expression
  message: {level, text}              $(error|warning|info …)
  when: {VAR: {any|none|any_except|none_except: [patterns]}}
        {VAR: {equals|not_equals: value}}  {VAR: {defined: bool}}
        {make_expr: {op: ifeq|ifneq, left, right}}
  then: [rules], else: [rules]        (with when)
Everything that is still Make syntax carries the key `make_expr`, so it is
visible and countable.
"""

import argparse
import json
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(RIOTBASE, "build-poc", "resolver"))
from translate_deps import translate  # noqa: E402

HEADER = ("# Generated from {yaml} by dist/tools/riot_deps/riot_deps.py.\n"
          "# Do not edit: change the YAML and run `just generate-deps`.\n\n")
COND_KEYS = {"any": "any", "none": "none", "any_out": "any_except",
             "none_out": "none_except"}


def yaml_name(dep_path: str) -> str:
    d, base = os.path.split(dep_path)
    if base == "Makefile.dep":
        return os.path.join(d, "deps.yaml")
    if base.startswith("Makefile.") and base.endswith(".dep"):
        return os.path.join(d, base[len("Makefile."):-len(".dep")] + ".deps.yaml")
    raise ValueError(f"unexpected dependency file name {dep_path}")


def dep_name(yaml_path: str) -> str:
    d, base = os.path.split(yaml_path)
    if base == "deps.yaml":
        return os.path.join(d, "Makefile.dep")
    if base.endswith(".deps.yaml"):
        return os.path.join(d, "Makefile." + base[:-len(".deps.yaml")] + ".dep")
    raise ValueError(f"unexpected YAML file name {yaml_path}")


# --- items (resolver) -> YAML ----------------------------------------------
def cond_to_yaml(c: dict) -> dict:
    (k, v), = c.items()
    if k in COND_KEYS:
        return {v[0]: {COND_KEYS[k]: list(v[1])}}
    if k in ("eq", "ne"):
        return {v[0]: {"equals" if k == "eq" else "not_equals": v[1]}}
    if k in ("def", "undef"):
        return {v: {"defined": k == "def"}}
    if k == "expr":
        return {"make_expr": {"op": v[0], "left": v[1], "right": v[2]}}
    raise ValueError(f"condition {k}")


def items_to_yaml(items: list) -> list:
    out = []
    for it in items:
        n_before = len(out)
        last_add = out[-1] if out else None
        if "note" in it:
            out.append({"comment": it["note"]})
            continue
        if "if" in it:
            r = {"when": cond_to_yaml(it["if"]), "then": items_to_yaml(it["then"])}
            if it["else"]:
                r["else"] = items_to_yaml(it["else"])
            out.append(r)
        elif "assign" in it:
            if it.get("export") or it.get("override") or it.get("define"):
                raise ValueError(f"export/override/define not supported: {it}")
            if "expr" in it:
                out.append({"assign": {"var": it["assign"], "op": it["op"],
                                       "make_expr": it["expr"]}})
            elif it["op"] == "+=":
                if out and set(out[-1]) == {"add"} and it["assign"] in out[-1]["add"] \
                        and "comment" not in it:
                    out[-1]["add"][it["assign"]] += it["words"]
                else:
                    out.append({"add": {it["assign"]: list(it["words"])}})
            else:
                out.append({"assign": {"var": it["assign"], "op": it["op"],
                                       "value": " ".join(it["words"])}})
        elif "include" in it:
            r = {"include": list(it["include"])}
            if it["optional"]:
                r["optional"] = True
            out.append(r)
        elif "include_expr" in it:
            r = {"include_make_expr": it["include_expr"]}
            if it["optional"]:
                r["optional"] = True
            out.append(r)
        elif "message" in it:
            out.append({"message": {"level": it["message"], "text": it["text"]}})
        else:
            raise ValueError(f"not representable: {it}")
        if "comment" in it and len(out) > n_before:
            out[-1] = {"comment": it["comment"], **out[-1]}
        elif "comment" in it and last_add is not None:
            last_add.setdefault("comment", it["comment"])
    return out


# --- YAML -> items (resolver) -----------------------------------------------
def cond_from_yaml(c: dict) -> dict:
    if "make_expr" in c:
        e = c["make_expr"]
        return {"expr": [e["op"], e["left"], e["right"]]}
    (var, spec), = c.items()
    (k, v), = spec.items()
    inv = {b: a for a, b in COND_KEYS.items()}
    if k in inv:
        return {inv[k]: [var, list(v)]}
    if k in ("equals", "not_equals"):
        return {"eq" if k == "equals" else "ne": [var, str(v)]}
    if k == "defined":
        return {"def" if v else "undef": var}
    raise ValueError(f"condition {c}")


def yaml_to_items(rules: list) -> list:
    out = []
    for r in rules:
        n_before = len(out)
        if set(r) == {"comment"}:
            out.append({"note": r["comment"]})
            continue
        if "when" in r:
            out.append({"if": cond_from_yaml(r["when"]),
                        "then": yaml_to_items(r.get("then", [])),
                        "else": yaml_to_items(r.get("else", []))})
        elif "add" in r:
            for var, words in r["add"].items():
                out.append({"assign": var, "op": "+=",
                            "words": [str(w) for w in words]})
        elif "assign" in r:
            a = r["assign"]
            if "make_expr" in a:
                out.append({"assign": a["var"], "op": a["op"], "expr": a["make_expr"]})
            else:
                out.append({"assign": a["var"], "op": a["op"],
                            "words": str(a["value"]).split()})
        elif "include" in r:
            out.append({"include": list(r["include"]),
                        "optional": bool(r.get("optional"))})
        elif "include_make_expr" in r:
            out.append({"include_expr": r["include_make_expr"],
                        "optional": bool(r.get("optional"))})
        elif "message" in r:
            out.append({"message": r["message"]["level"], "text": r["message"]["text"]})
        else:
            raise ValueError(f"unknown rule {r}")
        if "comment" in r and len(out) > n_before:
            out[n_before]["comment"] = r["comment"]
    return out


def load_yaml(path: str) -> list:
    doc = yaml.safe_load(open(path))
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError(f"{path}: schema_version 1 expected")
    return yaml_to_items(doc.get("rules") or [])


# --- items -> Makefile.dep (Make adapter) ------------------------------------
def cond_to_make(c: dict) -> str:
    (k, v), = c.items()
    if k in ("any", "none"):
        return f"{'ifneq' if k == 'any' else 'ifeq'} (,$(filter {' '.join(v[1])},$({v[0]})))"
    if k in ("any_out", "none_out"):
        return f"{'ifneq' if k == 'any_out' else 'ifeq'} (,$(filter-out {' '.join(v[1])},$({v[0]})))"
    if k in ("eq", "ne"):
        return f"{'ifeq' if k == 'eq' else 'ifneq'} ($({v[0]}),{v[1]})"
    if k == "def":
        return f"ifdef {v}"
    if k == "undef":
        return f"ifndef {v}"
    if k == "expr":
        return f"{v[0]} ({v[1]},{v[2]})"
    raise ValueError(k)


def items_to_make(items: list, depth: int = 0) -> list:
    pad = "  " * depth
    out = []
    for it in items:
        for line in (it.get("comment") or it.get("note") or "").split("\n") \
                if ("comment" in it or "note" in it) else []:
            out.append(f"{pad}# {line}".rstrip())
        if "note" in it:
            continue
        if "if" in it:
            out.append(pad + cond_to_make(it["if"]))
            out += items_to_make(it["then"], depth + 1)
            if it["else"]:
                out.append(pad + "else")
                out += items_to_make(it["else"], depth + 1)
            out.append(pad + "endif")
        elif "assign" in it:
            line = f"{pad}{it['assign']} {it['op']} " + \
                (it["expr"] if "expr" in it else " ".join(it["words"]))
            if it["op"] == "+=" and "words" in it and len(line) > 80:
                # one `VAR += word` per line (same meaning, RIOT line length)
                out += [f"{pad}{it['assign']} += {w}" for w in it["words"]]
            else:
                out.append(line.rstrip())
        elif "include" in it or "include_expr" in it:
            kw = "-include" if it["optional"] else "include"
            out.append(f"{pad}{kw} {it.get('include_expr') or ' '.join(it['include'])}")
        elif "message" in it:
            out.append(f"{pad}$({it['message']} {it['text']})")
    return out


def normalise(items: list) -> list:
    """Items without line numbers and bookkeeping keys, for comparison."""
    out = []
    for it in items:
        if "note" in it:
            continue
        it = {k: v for k, v in it.items() if k not in ("line", "chained", "comment")}
        if "if" in it:
            it["then"] = normalise(it["then"])
            it["else"] = normalise(it["else"])
        out.append(it)
    # adjacent `VAR += …` of the same variable are equivalent to one
    merged = []
    for it in out:
        if merged and it.get("op") == "+=" and "words" in it and \
                merged[-1].get("op") == "+=" and "words" in merged[-1] and \
                merged[-1]["assign"] == it["assign"] and set(it) == set(merged[-1]):
            merged[-1] = dict(merged[-1], words=merged[-1]["words"] + it["words"])
        else:
            merged.append(it)
    return merged


def count_make_expr(rules) -> int:
    if isinstance(rules, dict):
        return sum(count_make_expr(v) for v in rules.values()) + \
            (1 if any(k in rules for k in ("make_expr", "include_make_expr")) else 0)
    if isinstance(rules, list):
        return sum(count_make_expr(v) for v in rules)
    return 0


def cmd_export(args) -> int:
    for dep in args.files:
        items = translate(open(dep).read(), dep, unsupported := [])
        if unsupported:
            print(f"error: {dep}: unsupported: {unsupported[0]['text']}", file=sys.stderr)
            return 1
        rules = items_to_yaml(items)
        # the round trip must reproduce the same rules
        if normalise(yaml_to_items(rules)) != normalise(items):
            print(f"error: {dep}: YAML round trip differs", file=sys.stderr)
            return 1
        y = yaml_name(dep)
        with open(y, "w") as f:
            f.write(f"# Dependency rules of {os.path.relpath(os.path.dirname(os.path.abspath(dep)), RIOTBASE) or '.'}"
                    " (authoritative; Makefile.dep is generated from this file).\n")
            yaml.safe_dump({"schema_version": 1, "rules": rules}, f,
                           sort_keys=False, default_flow_style=None, width=100)
        print(f"{y}: {count_make_expr(rules)} Make expression(s) kept")
    return 0


def all_yaml() -> list:
    out = subprocess.run(["git", "-C", RIOTBASE, "ls-files", "--cached", "--others",
                          "--exclude-standard", "*deps.yaml"],
                         stdout=subprocess.PIPE, text=True, check=True).stdout.split()
    return [os.path.join(RIOTBASE, p) for p in sorted(out)]


def cmd_generate(args) -> int:
    files = all_yaml() if args.all else args.files
    failed = 0
    for y in files:
        try:
            items = load_yaml(y)
        except (ValueError, yaml.YAMLError) as e:
            print(f"error: {y}: {e}", file=sys.stderr)
            failed += 1
            continue
        text = HEADER.format(yaml=os.path.basename(y)) + "\n".join(items_to_make(items)) + "\n"
        dep = dep_name(y)
        current = open(dep).read() if os.path.exists(dep) else None
        if args.check:
            if current != text:
                print(f"{dep} is not up to date with {os.path.basename(y)}", file=sys.stderr)
                failed += 1
        elif current != text:
            tmp = dep + ".tmp"
            with open(tmp, "w") as f:
                f.write(text)
            os.replace(tmp, dep)
    return 1 if failed else 0


def cmd_items(args) -> int:
    json.dump(load_yaml(args.file), sys.stdout, indent=1)
    print()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("export")
    c.add_argument("files", nargs="+")
    c.set_defaults(func=cmd_export)
    c = sub.add_parser("generate")
    c.add_argument("--check", action="store_true")
    c.add_argument("--all", action="store_true")
    c.add_argument("files", nargs="*")
    c.set_defaults(func=cmd_generate)
    c = sub.add_parser("items")
    c.add_argument("file")
    c.set_defaults(func=cmd_items)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
