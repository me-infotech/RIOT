# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""Evaluation of the build data (step G3-1), on top of the resolver of G0-2.

The build data are rule lists of the configuration data format (schema 3,
dist/tools/config_data/README.md) in YAML files next to the Make files
whose build part they describe:

  Make file                         build data
  Makefile.include                  build.yaml           (Make keeps its file)
  <x>.inc.mk, <x>.mk (makefiles/)   <x>.build.yaml       (Make keeps its file)
  module Makefile, <x>.mk           module.yaml, <x>.module.yaml
                                    (the Make file is generated from it)
  package Makefile, Makefile.<x>    pkg.yaml, <x>.pkg.yaml (Make keeps its file)

An `include` of a Make file reads its build data; if there is none, the
include falls back to the resolver's data (deps.yaml, …, `.inc.yaml`). A Make
file without any data is outside the scope (OutOfScope); the evaluator only
tests whether it exists, it never opens it.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for sub in ("resolver", "config_data"):
    if os.path.join(TOOLS, sub) not in sys.path:
        sys.path.insert(0, os.path.join(TOOLS, sub))

# pylint: disable=wrong-import-position
import rules as R  # noqa: E402
from evaluate import Evaluator, OutOfScope, ResolveError, rel  # noqa: E402,F401
from variables import Variables  # noqa: E402

RIOTBASE = R.RIOTBASE


def build_yaml_name(make_path: str) -> str:
    """The build data file of a Make file (see the table above)."""
    directory, base = os.path.split(make_path)
    if base == "Makefile.include":
        return os.path.join(directory, "build.yaml")
    for suffix in (".inc.mk", ".mk"):
        if base.endswith(suffix) and len(base) > len(suffix):
            return os.path.join(directory, base[:-len(suffix)] + ".build.yaml")
    raise ValueError(f"no build data name for {make_path}")


def pkg_yaml_name(make_path: str) -> str:
    """The package data file of a package Make file: `pkg/<name>/Makefile` ->
    `pkg.yaml`, `Makefile.<x>` -> `<x>.pkg.yaml`."""
    directory, base = os.path.split(make_path)
    if base == "Makefile":
        return os.path.join(directory, "pkg.yaml")
    if base.startswith("Makefile.") and len(base) > len("Makefile."):
        return os.path.join(directory, base[len("Makefile."):] + ".pkg.yaml")
    raise ValueError(f"no package data name for {make_path}")


class BuildVariables(Variables):
    """Variables with providers: a variable that the data does not define
    but a provider knows (the toolchain probes PROBE_*, values of the build
    algorithm) is computed when it is first read, as Make expands a
    `$(shell …)` only when the variable is used."""

    def __init__(self, providers: dict = None):
        super().__init__()
        self.providers = dict(providers or {})
        self.provided: dict = {}

    def get(self, name: str) -> str:
        if not self.defined(name) and name in self.providers:
            if name not in self.provided:
                self.provided[name] = self.providers[name](self)
            return self.provided[name]
        return super().get(name)


class BuildEvaluator(Evaluator):
    """The resolver's evaluator with the build data mapping of includes and
    LAST_MAKEFILEDIR (the directory of the Make file read last)."""

    def run_file(self, yaml_path: str):
        self.v.set("LAST_MAKEFILEDIR", os.path.dirname(os.path.abspath(yaml_path)), "simple")
        super().run_file(yaml_path)

    def include_one(self, path: str, optional: bool, where: str):
        name = rel(path)
        if name in self.hooks:
            self.hooks[name]()
            return
        for kind in (build_yaml_name, R.module_yaml_name):
            try:
                data = kind(path)
            except ValueError:
                continue
            if os.path.isfile(data):
                self.run_file(data)
                return
        super().include_one(path, optional, where)
