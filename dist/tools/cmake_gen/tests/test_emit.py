# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""G1-G2: the CMake code written from a plan (no CMake needed)."""

import os
import re
import shlex
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import emit  # noqa: E402

PLAN = {
    "application": "app", "board": "nrf52840dk",
    "headers": [
        {"output": "/b/riotbuild/riotbuild.h.in", "always": True,
         "command": "'/t/genconfigheader.sh' -DA=\\\"x\\\" | '/t/lazysponge.py' '/b/r.h.in'"},
        {"output": "/b/riotbuild/riotbuild.h", "depends": ["/b/riotbuild/riotbuild.h.in"],
         "command": "sed -n -e '1i /* x */' a > b"},
    ],
    "modules": [{"name": "core", "data": "core/module.yaml", "objects": [
        {"source": "/r/core/a.c", "object": "/b/core/a.o", "cwd": "/r/core",
         "command": "gcc -DX=\\\"y\\\" -include '/b/r.h' -MQ '/b/core/a.o' -c -o /b/core/a.o "
                    "/r/core/a.c"}]}],
    "link": {"output": "/b/app.elf", "map": "/b/app.map", "depends": ["/b/core/a.o"],
             "command": "gcc /b/core/a.o -lm -o /b/app.elf"},
    "files": [{"output": "/b/app.bin", "command": "objcopy -Obinary /b/app.elf /b/app.bin"}],
    "size": "size /b/app.elf",
}


class QuoteTest(unittest.TestCase):

    def test_cmake_quoting(self):
        self.assertEqual(emit.q('a"b\\c$d;e'), '"a\\"b\\\\c\\$d\\;e"')

    def test_arguments_are_the_shell_words(self):
        self.assertEqual(emit.args("gcc -DX=\\\"y\\\" -include '/b/r.h'"),
                         '"gcc" "-DX=\\"y\\"" "-include" "/b/r.h"')


class CMakeTextTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = emit.cmake_text(PLAN, ["/r/build.yaml"])

    def test_object_command(self):
        self.assertIn('add_custom_command(OUTPUT "/b/core/a.o"', self.text)
        self.assertIn('  DEPFILE "/b/core/a.d"', self.text)
        self.assertIn('  WORKING_DIRECTORY "/r/core"', self.text)
        self.assertIn('DEPENDS "/r/core/a.c" "/b/riotbuild/riotbuild.h"', self.text)

    def test_header_steps(self):
        self.assertIn("add_custom_target(riot_riotbuild_h_in", self.text)
        self.assertIn('BYPRODUCTS "/b/riotbuild/riotbuild.h.in"', self.text)
        self.assertIn('DEPENDS "/b/riotbuild/riotbuild.h.in" riot_riotbuild_h_in', self.text)
        self.assertIn('COMMAND /bin/sh -c "sed -n -e \'1i /* x */\' a > b"', self.text)

    def test_link_files_and_size(self):
        self.assertIn('add_custom_command(OUTPUT "/b/app.elf"', self.text)
        self.assertIn('BYPRODUCTS "/b/app.map"', self.text)
        self.assertIn('add_custom_target(riot_all ALL DEPENDS "/b/app.elf" "/b/app.bin")',
                      self.text)
        self.assertIn('COMMAND "size" "/b/app.elf"', self.text)

    def test_reconfigure_on_data_change(self):
        self.assertIn('CMAKE_CONFIGURE_DEPENDS\n  "/r/build.yaml"', self.text)

    def test_commands_round_trip_to_the_plan_words(self):
        line = next(x for x in self.text.split("\n") if x.startswith('  COMMAND "gcc" "-DX'))
        words = [re.sub(r"\\(.)", r"\1", w)
                 for w in re.findall(r'"((?:\\.|[^"\\])*)"', line.split("COMMAND ", 1)[1])]
        self.assertEqual(words, shlex.split(PLAN["modules"][0]["objects"][0]["command"]))


class ProjectTextTest(unittest.TestCase):

    def test_project_runs_the_generator_and_uses_no_language(self):
        text = emit.project_text("riot_app", "/usr/bin/python3", "/r/cmake_gen.py", "/r/app",
                                 {"BOARD": "nrf52840dk", "BUILD_DIR": "/x"})
        self.assertIn("project(riot_app LANGUAGES NONE)", text)
        self.assertIn('COMMAND "/usr/bin/python3" "/r/cmake_gen.py" "plan" "-C" "/r/app" '
                      '"BOARD=nrf52840dk" "BUILD_DIR=/x"', text)
        self.assertIn('"BINDIR=${CMAKE_BINARY_DIR}"', text)
        self.assertIn("cmake_policy(SET CMP0116 OLD)", text)
        self.assertIn('include("${CMAKE_BINARY_DIR}/riot-build.cmake")', text)


if __name__ == "__main__":
    unittest.main()
