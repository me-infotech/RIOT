# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Evaluation of the rules of the configuration data (YAML only).

`Evaluator.run()` executes a rule list of the data format in order:
conditions, `add`, `set`, messages and `include`. An `include` names a Make
file; the evaluator reads the YAML next to it (dist/tools/config_data,
`rules.yaml_name`), validated against the schema. Three kinds of include
are not data:

  * steps of the build system's algorithm, implemented in Python
    (`hooks`: the pipeline for `Makefile.include`, the features check for
    `makefiles/features_check.inc.mk`);
  * Make files that only set build flags and change none of the resolved
    values (`MAKE_ONLY`); they are skipped and listed in the state;
  * anything else without YAML: `OutOfScope` - the data does not cover the
    request. The evaluator only tests whether such a Make file exists
    (os.path.exists) to tell "outside the data" from "optional and
    missing"; it never opens a Make file.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "config_data"))

# pylint: disable=wrong-import-position
import rules as R  # noqa: E402
import schema  # noqa: E402
from variables import keep  # noqa: E402

RIOTBASE = R.RIOTBASE

# Make files included by the data that only add compiler flags (group 3,
# build): they change no module, package, feature or CPU variable.
MAKE_ONLY = {
    "makefiles/default-radio-settings.inc.mk":
        "CFLAGS for the radio channel and PAN ID (examples/networking/gnrc/networking)",
}


_CACHE: dict = {}                 # (path, mtime) -> validated rules


class ResolveError(Exception):
    """An error of the configuration (what Make reports with `$(error …)`)."""


class OutOfScope(ResolveError):
    """The data does not cover the request (a file is not converted yet)."""


def rel(path: str) -> str:
    return os.path.relpath(os.path.normpath(path), RIOTBASE)


class Evaluator:
    """Runs rule lists on a Variables store."""

    def __init__(self, variables, curdir: str, hooks: dict = None):
        self.v = variables
        self.curdir = curdir
        self.hooks = dict(hooks or {})
        self.read: list = []          # YAML files read, in order
        self.skipped: list = []       # MAKE_ONLY files
        self.messages: list = []      # (level, text)

    # -- data files --------------------------------------------------------------
    def load(self, yaml_path: str) -> list:
        """The rules of a YAML file, validated (cached while the file is
        unchanged)."""
        key = (yaml_path, os.stat(yaml_path).st_mtime_ns)
        if key not in _CACHE:
            document = R.load_yaml(yaml_path)
            problems = schema.validate(document)
            if problems:
                raise ResolveError(f"{rel(yaml_path)}: " + "; ".join(problems[:3]))
            _CACHE[key] = document["rules"]
        self.read.append(rel(yaml_path))
        return _CACHE[key]

    def run_file(self, yaml_path: str):
        self.run(self.load(yaml_path), rel(yaml_path))

    # -- conditions ------------------------------------------------------------------
    def condition(self, cond: dict) -> bool:
        (key, value), = cond.items()
        v = self.v
        if key == "not":
            return not self.condition(value)
        if key == "has":
            return bool(v.select(value))
        if key == "several":
            return len(set(v.select(value))) > 1
        if key == "selection_equals":
            return v.select(value) == value["words"]
        if key == "one_of":
            # the words of the variable are the patterns, the values the words
            return bool(keep(v.words(value["var"]), value["values"]))
        if key == "equals":
            # each value compared word by word (blanks around it do not count)
            return all(" ".join(v.words(name)) == " ".join(val.split())
                       for name, val in value.items())
        raise ResolveError(f"unknown condition {key}")

    # -- rules --------------------------------------------------------------------------
    def run(self, rules: list, where: str = "rules"):
        for rule in rules:
            if "if" in rule:
                self.run(self._branch(rule), where)
            elif "add" in rule:
                (name, items), = rule["add"].items()
                for item in items:
                    self.v.add(name, item)
            elif "set" in rule:
                s = rule["set"]
                self.v.set(s["var"], s["value"], s.get("flavor", "recursive"))
            elif "include" in rule:
                self.include(rule["include"], where)
            elif "error" in rule:
                raise ResolveError(f"{where}: {self.v.text(rule['error'])}")
            elif "warning" in rule or "info" in rule:
                level = "warning" if "warning" in rule else "info"
                self.messages.append((level, self.v.text(rule[level])))

    def _branch(self, rule: dict) -> list:
        if self.condition(rule["if"]):
            return rule.get("then") or []
        for branch in rule.get("elif") or []:
            if self.condition(branch["if"]):
                return branch.get("then") or []
        return rule.get("else") or []

    # -- include ----------------------------------------------------------------------
    def include_paths(self, inc: dict) -> list:
        if "for_each" not in inc:
            return self.v.text(inc["path"]).split()
        # one path per word, `%` replaced by the word
        words = self.v.words(inc["for_each"])
        if inc.get("sort"):
            words = sorted(set(words))
        return [self.v.text(inc["path"]).replace("%", w, 1) for w in words]

    def include(self, inc: dict, where: str):
        for path in self.include_paths(inc):
            if not os.path.isabs(path):
                path = os.path.join(self.curdir, path)
            self.include_one(os.path.normpath(path), inc.get("optional", False), where)

    def include_one(self, path: str, optional: bool, where: str):
        name = rel(path)
        if name in self.hooks:
            self.hooks[name]()
            return
        if name in MAKE_ONLY:
            self.skipped.append(name)
            return
        try:
            yaml_path = os.path.join(os.path.dirname(path), os.path.basename(R.yaml_name(path)))
        except ValueError:
            yaml_path = None
        if yaml_path and os.path.isfile(yaml_path):
            self.run_file(yaml_path)
        elif os.path.exists(path):
            raise OutOfScope(f"{where}: includes {name}, which is not converted to data "
                             f"({rel(yaml_path) if yaml_path else 'no data file name'}); "
                             "the request is outside the scope of the data "
                             "(dist/tools/config_data/scope.yaml)")
        elif not optional:
            raise ResolveError(f"{where}: {name}: no such file")
