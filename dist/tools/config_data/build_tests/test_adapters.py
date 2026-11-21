#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""B4-B6, B8: the build data is the only source of the build part of the
board, CPU, build system and package Make files.

B4 register   every build/package data file is in scope.yaml `build` with
              the Make file it describes and its adapter
B5 one source the generated files are up to date; a split Make file includes
              its generated part once per section and holds none of its
              lines; stand-ins name Make files that are not generated
B6 round trip the generated Make has the rules of the original Make file
              (base commit) for the files written from it, and the Doxygen
              lines of the documented files
B8 stale      a changed data file, a hand-edited or missing generated file is
              found by `generate --check` (on a copy)

Run: python3 -m unittest discover -s dist/tools/config_data/build_tests -v
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# pylint: disable=wrong-import-position
import common as C  # noqa: E402
import generate  # noqa: E402
import rules as R  # noqa: E402
from translate import translate  # noqa: E402

CLI = os.path.join(C.TOOL, "config_data.py")


def build_data_files() -> list:
    listed = subprocess.run(["git", "-C", C.RIOTBASE, "ls-files", "--cached", "--others",
                             "--exclude-standard"], capture_output=True, text=True,
                            check=True).stdout.split()
    return sorted(p for p in listed if R.is_build_data_name(p))


ROOTS = {"$(RIOTBASE)/": "", "$(RIOTCPU)/": "cpu/", "$(RIOTBOARD)/": "boards/",
         "$(RIOTMAKE)/": "makefiles/"}


def included_path(line: str):
    """The repository path an `include` line names, or None."""
    if not line.startswith("include "):
        return None
    name = line[len("include "):].strip()
    for prefix, rel in ROOTS.items():
        if name.startswith(prefix):
            return rel + name[len(prefix):]
    return None


def includes_of(text: str, target: str) -> list:
    """The sections (None: no section) with which a Make file includes the
    generated file `target`."""
    found, section = [], None
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(generate.SECTION_VAR + " :="):
            section = line.split(":=", 1)[1].strip()
        elif included_path(line) == target:
            found.append(section)
            section = None
    return found


class RegisterTest(unittest.TestCase):
    """B4"""

    def test_every_data_file_is_registered(self):
        self.assertEqual(sorted(C.BUILD), build_data_files())
        self.assertEqual(len(C.BUILD), 35)

    def test_generate_and_check_read_every_data_file(self):
        import config_data  # pylint: disable=import-outside-toplevel
        known = {os.path.relpath(p, C.RIOTBASE) for p in config_data.all_data()}
        self.assertEqual(sorted(set(C.BUILD) - known), [])

    def test_entries(self):
        for data, entry in C.BUILD.items():
            with self.subTest(data=data):
                self.assertEqual(sorted(entry), ["adapter", "make"])
                self.assertIn(entry["adapter"], ("whole", "part", "none"))
                self.assertTrue(os.path.isfile(C.path(entry["make"])), entry["make"])
                self.assertEqual(os.path.dirname(entry["make"]), os.path.dirname(data))

    def test_none_means_every_rule_is_a_stand_in(self):
        for data, entry in C.BUILD.items():
            with self.subTest(data=data):
                empty = generate.for_make(C.rules_of(data)) == []
                self.assertEqual(entry["adapter"] == "none", empty)
                if entry["adapter"] == "none":
                    self.assertFalse(os.path.exists(C.path(data[:-5] + ".mk")))


class OneSourceTest(unittest.TestCase):
    """B5"""

    def test_up_to_date(self):
        res = subprocess.run([sys.executable, CLI, "generate", "--check"], capture_output=True,
                             text=True, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_generated_files_carry_the_header(self):
        for data in C.BUILD:
            target = C.generated(data)
            if target is None:
                continue
            with self.subTest(target=target):
                self.assertTrue(C.read(target).startswith(
                    f"# Generated from {os.path.basename(data)} by "
                    "dist/tools/config_data/config_data.py.\n# Do not edit"))

    def test_split_make_file_includes_each_section_once(self):
        for data, entry in C.BUILD.items():
            if entry["adapter"] != "part":
                continue
            sections = [r["section"] for r in C.rules_of(data) if "section" in r]
            target = C.generated(data)
            with self.subTest(make=entry["make"]):
                self.assertEqual(includes_of(C.read(entry["make"]), target), sections or [None])

    def test_split_make_file_holds_no_line_of_its_generated_part(self):
        for data, entry in C.BUILD.items():
            if entry["adapter"] != "part":
                continue
            generated = set(C.code_lines(C.read(C.generated(data))))
            # a condition may stand in both: the Make file keeps the part of a
            # conditional block that is not data
            generated = {line for line in generated if not line.startswith(
                ("ifeq", "ifneq", "ifdef", "ifndef", "else", "endif", generate.SECTION_VAR))}
            kept = C.code_lines(C.read(entry["make"]))
            with self.subTest(make=entry["make"]):
                self.assertEqual(sorted(generated & set(kept)), [])

    def test_stand_ins_name_make_files_that_are_not_generated(self):
        whole = {e["make"] for e in C.BUILD.values() if e["adapter"] == "whole"}
        for data in C.BUILD:
            for rule in R.walk(C.rules_of(data)):
                if generate.STAND_IN in rule:
                    with self.subTest(data=data, stand_in=rule[generate.STAND_IN]):
                        self.assertTrue(os.path.isfile(C.path(rule[generate.STAND_IN])))
                        self.assertNotIn(rule[generate.STAND_IN], whole)

    def test_providers_are_defined_once_and_used(self):
        text = C.read("makefiles/build_providers.inc.mk")
        defined = sorted(line.split(" =")[0] for line in text.split("\n")
                         if line[:1].isupper() and " = " in line)
        used = set()
        for data in C.BUILD:
            used.update(re.findall(r"\b(PROBE_[A-Z0-9_]+|BUILD_RIOT_VERSION_TUPLE|"
                                   r"BUILD_EXTDEFINES)\b", C.read(data)))
        self.assertEqual(sorted(n for n in defined if n != "COMPILER_INCLUDE_PATHS"),
                         sorted(used))
        sys.path.insert(0, os.path.join(C.TOOLS, "cmake_gen"))
        import plan  # noqa: E402  pylint: disable=import-outside-toplevel
        self.assertEqual(sorted(used - set(plan.PROVIDERS)), [])
        self.assertIn("include $(RIOTMAKE)/build_providers.inc.mk", C.read("Makefile.include"))


# whole files written from the Make file by the translator (comments kept)
TRANSLATED = ["boards/Makefile.include", "cpu/Makefile.include",
              "boards/common/nrf52xxxdk/Makefile.include",
              "sys/malloc_thread_safe/Makefile.include",
              "sys/net/gnrc/pktbuf_static/Makefile.include",
              "sys/net/sock/async/event/Makefile.include", "pkg/cmsis/Makefile.include",
              "pkg/mpaland-printf/Makefile.include",
              "drivers/netdev_ieee802154_submac/Makefile.include",
              "makefiles/pseudomodules.inc.mk"]
DOXYGEN = ["makefiles/pseudomodules.inc.mk", "drivers/netdev_ieee802154_submac/Makefile.include"]


class RoundTripTest(unittest.TestCase):
    """B6"""

    def data_of(self, make):
        return next(d for d, e in C.BUILD.items() if e["make"] == make)

    def original(self, make):
        text = C.git_show(C.BASE, make)
        if text is None:
            self.skipTest(f"base commit {C.BASE[:10]} not available")
        return text

    def test_original_equals_generated_equals_data(self):
        for make in TRANSLATED:
            with self.subTest(make=make):
                original = R.normalise(translate(self.original(make), make))
                self.assertEqual(R.normalise(translate(C.read(make), make)), original)
                self.assertEqual(R.normalise(C.rules_of(self.data_of(make))), original)

    def test_doxygen_lines_are_the_originals(self):
        for make in DOXYGEN:
            with self.subTest(make=make):
                doc = [line for line in C.read(make).split("\n") if line.startswith("##")]
                self.assertEqual(doc, [line for line in self.original(make).split("\n")
                                       if line.startswith("##")])
                self.assertGreater(len(doc), 0)

    def test_a_changed_rule_is_found(self):
        make = "boards/common/nrf52xxxdk/Makefile.include"
        rules = C.rules_of(self.data_of(make))
        changed = [dict(r) for r in rules]
        changed[0] = {"add": {"INCLUDES": ["-I/elsewhere"]}}
        self.assertNotEqual(R.normalise(changed),
                            R.normalise(translate(self.original(make), make)))


class StaleTest(unittest.TestCase):
    """B8: on a copy of the repository's data and Make files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "build.yaml")
        self.make = os.path.join(self.tmp.name, "build.mk")
        shutil.copy(C.path("cpu/nrf52/build.yaml"), self.data)
        shutil.copy(C.path("cpu/nrf52/build.mk"), self.make)

    def check(self):
        import config_data  # pylint: disable=import-outside-toplevel
        text = generate.make_text(config_data.load_valid(self.data), "build.yaml",
                                  "cpu/nrf52/Makefile.include")
        if not os.path.exists(self.make):
            return False
        with open(self.make, encoding="utf-8") as file:
            return file.read() == text

    def edit(self, path, old, new):
        with open(path, encoding="utf-8") as file:
            text = file.read()
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text.replace(old, new, 1))

    def test_copy_is_up_to_date(self):
        self.assertTrue(self.check())

    def test_data_changed(self):
        self.edit(self.data, "0x40000", "0x20000")
        self.assertFalse(self.check())

    def test_generated_file_edited(self):
        self.edit(self.make, "RAM_LEN ?= 0x40000", "RAM_LEN ?= 0x20000")
        self.assertFalse(self.check())

    def test_generated_file_missing(self):
        os.remove(self.make)
        self.assertFalse(self.check())

    def test_cli_reports_the_repository_state(self):
        res = subprocess.run([sys.executable, CLI, "generate", "--check", C.path("build.yaml")],
                             capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
