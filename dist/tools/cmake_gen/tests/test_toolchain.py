# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""T1-T2: toolchain probes, with stub tools on PATH (no real toolchain
needed): the same answers as Make's `$(shell …)` with and without the tool."""

import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import toolchain as T  # noqa: E402
from buildeval import BuildVariables, RIOTBASE  # noqa: E402

GCC = """#!/bin/sh
# stub arm-none-eabi-gcc: answers like gcc 13.3; logs its arguments
echo "$@" >> "$STUB_LOG"
case "$*" in
  -dumpversion) echo 13.3.1 ;;
  "-std=c11 -E -") exit 0 ;;
  "-std=c++14 -E -") exit 1 ;;
  "-specs=nano.specs -E -") exit 0 ;;
  "-v -x c -E /dev/null") printf '%s\\n' 'x' '#include <...> search starts here:' " $INC" 'End of search list.' >&2 ;;
  *noexecstack*) exit 0 ;;
  *no-warn-rwx*) exit 1 ;;
  *nano.specs*) echo "warning: use of wchar_t values across objects may fail" >&2 ;;
esac
"""


class ProbeTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        self.inc = os.path.join(self.tmp.name, "include")
        os.makedirs(os.path.join(self.inc, "newlib-nano"))
        open(os.path.join(self.inc, "newlib.h"), "w", encoding="utf-8").close()
        self.log = os.path.join(self.tmp.name, "log")

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, name, text):
        path = os.path.join(self.bin, name)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def v(self):
        v = BuildVariables(T.PROVIDERS)
        for name, value in (("PREFIX", "arm-none-eabi-"), ("CC", "arm-none-eabi-gcc"),
                            ("LINK", "arm-none-eabi-gcc"), ("TARGET_ARCH", "arm-none-eabi"),
                            ("RIOTTOOLS", os.path.join(RIOTBASE, "dist", "tools")),
                            ("RIOTBASE", RIOTBASE)):
            v.set(name, value, "simple")
        return v

    def env(self, with_path=True):
        path = self.bin + (os.pathsep + "/usr/bin:/bin" if with_path else "")
        return mock.patch.dict(os.environ, {"PATH": path, "STUB_LOG": self.log,
                                            "INC": self.inc})

    def test_answers_of_a_toolchain(self):
        self.tool("arm-none-eabi-gcc", GCC)
        self.tool("arm-none-eabi-objcopy", "#!/bin/sh\n")
        with self.env():
            v = self.v()
            self.assertEqual(v.get("PROBE_GCC_VERSION"), "13")
            self.assertEqual(v.get("PROBE_CC_STD_C11"), "0")
            self.assertEqual(v.get("PROBE_CC_STD_CXX14"), "1")
            self.assertEqual(v.get("PROBE_LINK_NOEXECSTACK"), "1")
            self.assertEqual(v.get("PROBE_LINK_NOWARNRWX"), "0")
            self.assertEqual(v.get("PROBE_LINK_NANO_SPECS"), "0")
            self.assertEqual(v.get("PROBE_LINK_NANO_WCHAR_WARNING"), "0")
            self.assertEqual(v.get("PROBE_NEWLIB_INCLUDE_DIR"), os.path.realpath(self.inc))
            v.set("NEWLIB_INCLUDE_DIR", self.inc, "simple")
            self.assertEqual(v.get("PROBE_NEWLIB_NANO_INCLUDE_DIR"),
                             os.path.join(self.inc, "newlib-nano"))
            self.assertEqual(v.get("PROBE_OBJCOPY"), os.path.join(self.bin, "arm-none-eabi-objcopy"))
        with open(self.log, encoding="utf-8") as file:
            calls = file.read().split("\n")
        self.assertIn("-dumpversion", calls)
        self.assertIn("-std=c11 -E -", calls)
        minimal = os.path.join(RIOTBASE, "dist", "tools", "testprogs", "minimal_linkable.c")
        self.assertIn(f"{minimal} -o /dev/null -lc -Wall -Wextra -pedantic -z noexecstack", calls)

    def test_answers_without_toolchain_are_makes(self):
        with self.env(with_path=False):
            v = self.v()
            self.assertEqual(v.get("PROBE_GCC_VERSION"), "")
            self.assertEqual(v.get("PROBE_CC_STD_C11"), "127")
            self.assertEqual(v.get("PROBE_LINK_NOEXECSTACK"), "0")
            self.assertEqual(v.get("PROBE_LINK_NOWARNRWX"), "0")
            self.assertEqual(v.get("PROBE_LINK_NANO_SPECS"), "127")
            self.assertEqual(v.get("PROBE_LINK_NANO_WCHAR_WARNING"), "1")
            self.assertEqual(v.get("PROBE_OBJCOPY"), "")
            self.assertEqual(v.get("PROBE_OBJDUMP"), "objdump")

    def test_objcopy_falls_back_to_the_host_tool(self):
        self.tool("objcopy", "#!/bin/sh\n")
        with self.env(with_path=False):
            self.assertEqual(self.v().get("PROBE_OBJCOPY"), os.path.join(self.bin, "objcopy"))

    def test_git_version_of_the_repository(self):
        v = self.v()
        if not os.path.exists(os.path.join(RIOTBASE, ".git")):
            self.skipTest("not a git checkout")
        self.assertTrue(v.get("PROBE_GIT_DESCRIBE"))
        v2 = BuildVariables(T.PROVIDERS)
        v2.set("RIOTBASE", self.tmp.name, "simple")
        self.assertEqual(v2.get("PROBE_GIT_DESCRIBE"), "")


if __name__ == "__main__":
    unittest.main()
