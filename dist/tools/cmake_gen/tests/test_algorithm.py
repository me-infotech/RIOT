# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""A1-A5: the build algorithm of plan.py on small trees (Makefile.base,
DIRS recursion, exported variables, modules.inc.mk, version tuple, link)."""

import os
import shlex
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import plan as P  # noqa: E402
from buildeval import BuildVariables, OutOfScope, ResolveError  # noqa: E402

ENV = {"CC": "cc", "CFLAGS": "-O2 -DX", "INCLUDES": "-I/inc", "BINDIR": "/bin/b",
       "USEMODULE": "", "RIOTBASE": P.RIOTBASE}


def touch(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def module_yaml(*rules):
    return "schema: 3\nrules:\n" + "".join(f"  - {r}\n" for r in rules) + \
        "  - include: {path: '${RIOTBASE}/Makefile.base'}\n"


class MakefileBaseTest(unittest.TestCase):
    """A1: sources and objects as Makefile.base computes them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "mymod")
        for name in ("b.c", "a.c", "init.c", "panic.c", "x.h"):
            touch(os.path.join(self.dir, name))

    def tearDown(self):
        self.tmp.cleanup()

    def base(self, **values):
        env = dict(ENV)
        env.update({k: v for k, v in values.items() if k in ENV})
        v = P.child(env, {}, self.dir)
        for name, value in values.items():
            if name not in ENV:
                v.set(name, value, "simple")
        return P.makefile_base(v, self.dir)

    def sources(self, module):
        return [os.path.basename(o["source"]) for o in module["objects"]]

    def test_automatic_sources_and_module_name(self):
        module = self.base()
        self.assertEqual(module["name"], "mymod")
        self.assertEqual(self.sources(module), ["a.c", "b.c", "init.c", "panic.c"])
        self.assertEqual(module["objects"][0]["object"], "/bin/b/mymod/a.o")

    def test_explicit_sources_and_module(self):
        module = self.base(MODULE="other", SRC="b.c sub/c.c")
        self.assertEqual(self.sources(module), ["b.c", "c.c"])
        self.assertEqual(module["objects"][1]["object"], "/bin/b/other/sub/c.o")

    def test_submodules(self):
        module = self.base(SUBMODULES="1", BASE_MODULE="core", SRC="b.c",
                           USEMODULE="core_init core_panic core_missing other")
        self.assertEqual(self.sources(module), ["b.c", "init.c", "panic.c"])
        module = self.base(SUBMODULES="1", BASE_MODULE="core", USEMODULE="core_init core_panic",
                           SUBMODULES_NO_SRC="panic.c")
        self.assertEqual(self.sources(module), ["init.c"])
        # no automatic *.c with SUBMODULES, even without a submodule
        self.assertEqual(self.sources(self.base(SUBMODULES="1")), [])

    def test_no_auto_src_and_nolto(self):
        module = self.base(NO_AUTO_SRC="1", SRC_NOLTO="b.c", LTOFLAGS="-flto")
        self.assertEqual(self.sources(module), ["b.c"])
        self.assertNotIn("-flto", module["objects"][0]["command"])
        module = self.base(SRC="a.c", LTOFLAGS="-flto")
        self.assertIn("-flto", shlex.split(module["objects"][0]["command"]))
        # SRC_NOLTO files are not part of the automatic sources
        self.assertEqual(self.sources(self.base(SRC_NOLTO="b.c")), ["b.c", "a.c", "init.c",
                                                                    "panic.c"])

    def test_compile_command_is_makefile_base_rule(self):
        cmd = self.base(SRC="a.c", CCACHE="ccache")["objects"][0]["command"]
        self.assertEqual(shlex.split(cmd), ["ccache", "cc", "-O2", "-DX", "-I/inc", "-MQ",
                                            "/bin/b/mymod/a.o", "-MD", "-MP", "-c", "-o",
                                            "/bin/b/mymod/a.o", os.path.join(self.dir, "a.c")])

    def test_static_analysis_flags_go_first(self):
        cmd = self.base(SRC="a.c", STATIC_ANALYSIS="1", MODULE_SUPPORTS_STATIC_ANALYSIS="1",
                        CFLAGS_STATIC_ANALYSIS="-fanalyzer")["objects"][0]["command"]
        self.assertEqual(shlex.split(cmd)[1:3], ["-fanalyzer", "-O2"])

    def test_dirs_are_absolute_sorted_unique(self):
        module = self.base(DIRS="z a ../x a")
        self.assertEqual(module["dirs"], sorted([os.path.join(self.dir, "a"),
                                                 os.path.join(self.tmp.name, "x"),
                                                 os.path.join(self.dir, "z")]))

    def test_outside_the_step(self):
        touch(os.path.join(self.dir, "start.S"))
        with self.assertRaises(OutOfScope):
            self.base()
        with self.assertRaises(ResolveError):
            self.base(SRCXX="x.cpp", NO_AUTO_SRC="1")


class WalkTest(unittest.TestCase):
    """A2: the DIRS recursion with the exported variables of the parent."""

    def test_children_inherit_the_exported_values_of_their_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            top, sub = os.path.join(tmp, "top"), os.path.join(tmp, "top", "sub")
            touch(os.path.join(top, "t.c"))
            touch(os.path.join(sub, "s.c"))
            touch(os.path.join(top, "module.yaml"),
                  module_yaml("add: {CFLAGS: [-DTOP]}", "add: {DIRS: [sub]}",
                              "set: {var: NOT_EXPORTED, value: x}"))
            touch(os.path.join(sub, "module.yaml"),
                  module_yaml("if: {equals: {NOT_EXPORTED: x}}\n    then:\n"
                              "      - error: not exported"))
            modules, read = [], []
            P.walk_module(dict(ENV), {"BOARD": "b"}, top, os.path.join(top, "module.yaml"),
                          {}, modules, read, ["CFLAGS", "CC", "INCLUDES", "BINDIR", "RIOTBASE"])
            self.assertEqual([m["name"] for m in modules], ["top", "sub"])
            sub_cmd = shlex.split(modules[1]["objects"][0]["command"])
            self.assertIn("-DTOP", sub_cmd)
            self.assertEqual(modules[1]["objects"][0]["cwd"], sub)

    def test_module_without_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch(os.path.join(tmp, "Makefile"), "include $(RIOTBASE)/Makefile.base\n")
            with self.assertRaises(OutOfScope):
                P.walk_module(dict(ENV), {}, tmp, os.path.join(tmp, "module.yaml"), {}, [], [],
                              [])
            touch(os.path.join(tmp, "module.yaml"), "schema: 1\nrules:\n  - set: {var: A, "
                                                    "value: b}\n")
            with self.assertRaises(ResolveError):
                P.walk_module(dict(ENV), {}, tmp, os.path.join(tmp, "module.yaml"), {}, [], [],
                              [])


class ModulesTest(unittest.TestCase):
    """A3: modules.inc.mk, the version tuple."""

    def v(self, **values):
        v = BuildVariables()
        for name, value in values.items():
            v.set(name, value, "simple")
        return v

    def test_extdefines_sorted_with_packages(self):
        v = self.v(USEMODULE="zz core cortexm-x", USEPKG="mpaland-printf core")
        self.assertEqual(P.extdefines(v), "-DMODULE_CORE -DMODULE_CORTEXM_X "
                                          "-DMODULE_MPALAND_PRINTF -DMODULE_ZZ")

    def test_realmodules(self):
        v = self.v(USEMODULE="core core_lib auto_init_x auto_init_can periph_gpio",
                   USEPKG="cmsis", PSEUDOMODULES="core_% auto_init_% periph_% cmsis",
                   NO_PSEUDOMODULES="core_lib auto_init_can")
        self.assertEqual(P.realmodules(v), ["core", "auto_init_can", "core_lib"])

    def test_version_tuple(self):
        for version, expected in (("2027.01-devel-327-g984ebd-branch", "2027,1,0"),
                                  ("2026.04.08", "2026,4,8"), ("2026.10.1.5", "2026,10,1"),
                                  ("buildtest", ""), ("2026", ""), ("", ""),
                                  ("'UNKNOWN (builddir: /x)'", "")):
            with self.subTest(version=version):
                self.assertEqual(P.version_tuple(version), expected)

    def test_dummy_version_when_the_version_is_no_number(self):
        v = self.v(RIOT_VERSION="buildtest", RIOT_DUMMY_VERSION="2042.5.23")
        self.assertEqual(P.riot_version_tuple(v), "2042,5,23")


class AssembleTest(unittest.TestCase):
    """A4, A5: link order and line, module check, build files."""

    def v(self, **extra):
        values = {"APPLICATION": "app", "APPLICATION_MODULE": "application_app",
                  "USEMODULE": "core sys", "PSEUDOMODULES": "", "BINDIR": "/b", "LINK": "ld",
                  "LINKFLAGS": "-Tx.ld -Wl,--gc-sections", "LINKFLAGPREFIX": "-Wl,",
                  "ELFFILE": "/b/app.elf", "BINFILE": "/b/app.bin", "OBJCOPY": "objcopy",
                  "SIZE": "size", "BUILD_FILES": "/b/app.elf /b/app.bin /b/app.elf /b/app.bin",
                  "RIOTBUILD_CONFIG_HEADER_C": "/b/riotbuild/riotbuild.h", "RIOTTOOLS": "/t",
                  "LAZYSPONGE": "/t/lazysponge.py", "CFLAGS_WITH_MACROS": "-DA", **extra}
        v = BuildVariables()
        for name, value in values.items():
            v.set(name, value, "simple")
        return v

    @staticmethod
    def module(name, *objs):
        return {"name": name, "objects": [{"object": f"/b/{o}"} for o in objs]}

    def test_link_is_sorted_like_find_sort_in_c_locale(self):
        modules = [self.module("sys", "sys/z.o"), self.module("core", "core/b.o", "core/a.o"),
                   self.module("application_app", "application_app/main.o"),
                   self.module("core_lib", "core_lib/x.o"), self.module("extra", "extra/e.o")]
        plan = P.assemble(self.v(USEMODULE="core core_lib sys"), modules, [], [])
        self.assertEqual(plan["link"]["objects"],
                         ["/b/application_app/main.o", "/b/core/a.o", "/b/core/b.o",
                          "/b/core_lib/x.o", "/b/sys/z.o"])
        self.assertEqual(shlex.split(plan["link"]["command"])[-6:],
                         ["-lm", "-Tx.ld", "-Wl,--gc-sections", "-Wl,-Map=/b/app.map", "-o",
                          "/b/app.elf"])
        self.assertEqual([f["output"] for f in plan["files"]], ["/b/app.bin"])
        self.assertEqual(plan["files"][0]["command"], "objcopy -Obinary /b/app.elf /b/app.bin")
        self.assertEqual(plan["size"], "size /b/app.elf")

    def test_unknown_module_is_an_error(self):
        with self.assertRaises(ResolveError):
            P.assemble(self.v(USEMODULE="core missing"), [self.module("core")], [], [])

    def test_a_module_built_twice_is_an_error(self):
        with self.assertRaises(ResolveError):
            P.assemble(self.v(), [self.module("core"), self.module("core"),
                                  self.module("sys")], [], [])

    def test_pseudomodules_are_not_linked(self):
        plan = P.assemble(self.v(USEMODULE="core sys periph_init", PSEUDOMODULES="periph_%"),
                          [self.module("core", "core/a.o"), self.module("sys"),
                           self.module("periph_init", "periph_init/x.o")], [], [])
        self.assertEqual(plan["link"]["objects"], ["/b/core/a.o"])

    def test_headers(self):
        plan = P.assemble(self.v(BUILD_HEADERS="/b/pp/pp.h", RIOT_PP_SUCCESSOR_MAX="9"),
                          [self.module("core"), self.module("sys")], [], [])
        commands = [h["command"] for h in plan["headers"]]
        self.assertIn("'/t/genconfigheader/genconfigheader.sh' -DA | '/t/lazysponge.py' "
                      "'/b/riotbuild/riotbuild.h.in'", commands[0])
        self.assertTrue(commands[1].startswith("sed -n -e '1i /* Generated file do not edit */'"))
        self.assertTrue(commands[2].endswith("generate_pp_successor_header.sh' 9 > /b/pp/pp.h"))


if __name__ == "__main__":
    unittest.main()
