# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""P1-P5: parity of the build without Make with GNU Make on nrf52840dk.

P1  plan (data only) vs. Make's commands (golden files): the objects, the
    compile command of each object, link, objcopy, size, the commands that
    generate riotbuild.h and preprocessor_successor.h.
P2  the same for the commands Ninja runs (CMake configure + `ninja -t
    commands`, needs cmake and ninja, no toolchain, no network).
P3  the generated headers (built by Ninja, no toolchain) vs. Make's.
P4  live Make with the generated module Makefiles gives the golden commands
    (needs GNU Make; offline: the packages are stood in by empty files).
P5  the firmware (needs arm-none-eabi-gcc, GNU Make and the network for
    the packages): Make's and Ninja's `.bin` are byte-identical, the ELF
    files have the same sections and symbols.
"""

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
sys.path.insert(0, HERE)
import makeparity as M  # noqa: E402
import plan as P  # noqa: E402
import sample  # noqa: E402

CMAKE, NINJA, MAKE = shutil.which("cmake"), shutil.which("ninja"), shutil.which("make")
ARM = shutil.which("arm-none-eabi-gcc")
BUILD_DIR, BINDIR = "/nonexistent-g3/build", "/nonexistent-g3/bin/nrf52840dk"


def golden(app: str) -> dict:
    _, sections = sample.read_golden(sample.golden_path(app))
    return sections


def make_cmds(app: str) -> dict:
    text = sample.section(golden(app), sample.PREPARED)
    return M.make_commands(text, {}, sample.CC, sample.CC)


def plan_of(app: str, build_dir=BUILD_DIR, bindir=BINDIR) -> dict:
    return P.build_plan(os.path.join(P.RIOTBASE, sample.APPS[app]),
                        {"BOARD": sample.BOARD, "BUILD_DIR": build_dir, "BINDIR": bindir})


def mask_header(text: str) -> str:
    text = re.sub(r'#define RIOT_VERSION "[^"]*"', '#define RIOT_VERSION "@VERSION@"', text)
    return re.sub(r"#define RIOT_VERSION_CODE RIOT_VERSION_NUM\([0-9,]*\)",
                  "#define RIOT_VERSION_CODE RIOT_VERSION_NUM(@CODE@)", text)


def golden_host_matches() -> bool:
    """The goldens were recorded without arm-none-eabi-gcc (header line):
    the toolchain probes give the same answers only on such a host."""
    head, _ = sample.read_golden(sample.golden_path("hello-world"))
    recorded_without = "# arm-none-eabi-gcc: not installed" in head
    return recorded_without == (ARM is None)


GOLDEN_HOST = "goldens recorded on a host with another toolchain state (re-record them)"


@unittest.skipUnless(golden_host_matches(), GOLDEN_HOST)
class PlanParityTest(unittest.TestCase):
    """P1: the plan has Make's commands, for each application."""

    @classmethod
    def setUpClass(cls):
        cls.plans = {app: plan_of(app) for app in sample.APPS}

    def ours(self, app):
        mapping = {BINDIR: "@BINDIR@", BUILD_DIR: "@BUILD_DIR@", P.RIOTBASE: "@RIOTBASE@"}
        return M.plan_commands(self.plans[app], mapping)

    def test_same_commands(self):
        for app in sample.APPS:
            with self.subTest(app=app):
                self.assertEqual(M.compare(make_cmds(app), self.ours(app)), [])

    def test_object_counts(self):
        counts = {app: len(make_cmds(app)["compile"]) for app in sample.APPS}
        self.assertEqual(counts, {"hello-world": 44, "gnrc_networking": 153, "bindist": 45})
        for app in sample.APPS:
            self.assertEqual(len(self.ours(app)["compile"]), counts[app])

    def test_one_difference_is_found(self):
        # the comparison itself: a changed flag, a missing object, the link order
        make, ours = make_cmds("hello-world"), self.ours("hello-world")
        obj = sorted(ours["compile"])[0]
        ours["compile"][obj] = ours["compile"][obj][:-2] + ours["compile"][obj][-1:]
        self.assertEqual(len(M.compare(make, ours)), 1)
        ours = self.ours("hello-world")
        del ours["compile"][obj]
        self.assertTrue(any("only in Make" in p for p in M.compare(make, ours)))
        ours = self.ours("hello-world")
        ours["link"] = ours["link"][:2] + ours["link"][3:4] + ours["link"][2:3] + ours["link"][4:]
        self.assertTrue(any(p.startswith("link") for p in M.compare(make, ours)))

    def test_toolchain_answers_of_the_golden_host(self):
        # recorded without arm-none-eabi-gcc: the probes fail like Make's
        tc = self.plans["hello-world"]["toolchain"]
        self.assertEqual((tc["PROBE_GCC_VERSION"], tc["PROBE_CC_STD_C11"]), ("", "127"))


def ninja_lines(builddir: str, *targets) -> list:
    out = subprocess.run([NINJA, "-C", builddir, "-t", "commands", *targets],
                         capture_output=True, text=True, check=True).stdout
    lines = []
    for line in out.splitlines():
        if line.startswith("cd ") and " && " in line:
            line = line.split(" && ", 1)[1]
        if line.startswith("/bin/sh -c "):
            line = shlex.split(line)[2]
        lines.append(line)
    return lines


def configure(app: str, tmp: str) -> tuple:
    build_dir, builddir = os.path.join(tmp, "build"), os.path.join(tmp, "cmake")
    gen = [sys.executable, os.path.join(TOOL, "cmake_gen.py"), "generate", "-C",
           os.path.join(P.RIOTBASE, sample.APPS[app]), f"BOARD={sample.BOARD}", "-B", builddir,
           f"BUILD_DIR={build_dir}"]
    subprocess.run(gen, check=True, capture_output=True)
    subprocess.run([CMAKE, "-G", "Ninja", "-DRIOT_NO_PACKAGES=ON", "-S",
                    os.path.join(builddir, "project"), "-B", builddir],
                   check=True, capture_output=True)
    return build_dir, builddir


@unittest.skipUnless(golden_host_matches(), GOLDEN_HOST)
@unittest.skipIf(CMAKE is None or NINJA is None, "cmake and ninja are needed")
class NinjaParityTest(unittest.TestCase):
    """P2, P3: what Ninja runs, and the headers it generates."""

    def test_ninja_commands_and_headers(self):
        for app in sample.APPS:
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                build_dir, builddir = configure(app, tmp)
                mapping = {builddir: "@BINDIR@", build_dir: "@BUILD_DIR@",
                           P.RIOTBASE: "@RIOTBASE@"}
                lines = [M.mask_version(M.normalise_paths(line, mapping))
                         for line in ninja_lines(builddir, "riot_all", "riot_print_size")]
                ours = M.classify(lines, sample.CC, sample.CC)
                ours["link"] = shlex.split(ours["link"])
                self.assertEqual(M.compare(make_cmds(app), ours), [])
                # P3: the headers (no toolchain needed)
                header = os.path.join(builddir, "riotbuild", "riotbuild.h")
                pp_header = os.path.join(builddir, "preprocessor", "preprocessor_successor.h")
                subprocess.run([NINJA, "-C", builddir, header, pp_header], check=True,
                               capture_output=True)
                with open(header, encoding="utf-8") as file:
                    text = M.normalise_paths(file.read().rstrip("\n"), mapping)
                expected = sample.section(golden(app), sample.RIOTBUILD_H)
                self.assertEqual(mask_header(text), mask_header(expected))
                with open(pp_header, "rb") as file:
                    data = file.read()
                self.assertEqual(sample.section(golden(app), sample.PP_H).split("\n"),
                                 [f"sha256 {hashlib.sha256(data).hexdigest()}",
                                  f"lines {data.count(b'\n')}"])

    def test_cmake_runs_no_make_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, builddir = configure("hello-world", tmp)
            with open(os.path.join(builddir, "CMakeCache.txt"), encoding="utf-8") as file:
                cache = file.read()
            program = re.search(r"^CMAKE_MAKE_PROGRAM:FILEPATH=(.*)$", cache, re.M).group(1)
            self.assertEqual(os.path.basename(program), "ninja")
            self.assertIn("CMAKE_GENERATOR:INTERNAL=Ninja", cache)


def stand_in_packages(plan: dict):
    """Empty files in place of the prepared packages: Make's state files,
    sparse tags, copied headers and the package sources (P4, offline)."""
    for spec in plan["packages"]:
        src = spec["source_dir"]
        os.makedirs(os.path.join(src, ".git"), exist_ok=True)
        if spec["sparse_paths"]:
            with open(f"{src}.sparse", "w", encoding="utf-8") as file:
                file.write(" ".join(spec["sparse_paths"]) + "\n")
        for state in ("downloaded", "patched", "patched.d", "prepared"):
            open(os.path.join(src, f".pkg-state.git-{state}"), "w", encoding="utf-8").close()
        if spec.get("copy"):
            os.makedirs(spec["copy"]["to"], exist_ok=True)
            for name in spec["copy"]["files"]:
                open(os.path.join(spec["copy"]["to"], name), "w", encoding="utf-8").close()
    for module in plan["modules"]:
        for obj in module["objects"]:
            if not os.path.exists(obj["source"]):
                os.makedirs(os.path.dirname(obj["source"]), exist_ok=True)
                open(obj["source"], "w", encoding="utf-8").close()


@unittest.skipUnless(golden_host_matches(), GOLDEN_HOST)
@unittest.skipIf(MAKE is None, "GNU Make is not installed")
class LiveMakeTest(unittest.TestCase):
    """P4: Make with the generated module Makefiles still runs the commands
    of the golden files (recorded on the base commit, before the
    conversion)."""

    def test_make_with_generated_module_makefiles(self):
        for app, app_dir in sample.APPS.items():
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                build_dir, bindirbase = os.path.join(tmp, "build"), os.path.join(tmp, "bin")
                bindir = os.path.join(bindirbase, sample.BOARD)
                stand_in_packages(plan_of(app, build_dir, bindir))
                extra = [f"BUILD_DIR={build_dir}", f"BINDIRBASE={bindirbase}"]
                header = os.path.join(bindir, "riotbuild", "riotbuild.h")
                for goals in ([header], ["-n", "-k"]):
                    res = subprocess.run(sample.make_argv(app_dir, extra + goals),
                                         cwd=P.RIOTBASE, env=sample.environment(),
                                         capture_output=True, text=True, check=False)
                text = res.stdout + res.stderr
                mapping = {bindir: "@BINDIR@", build_dir: "@BUILD_DIR@",
                           P.RIOTBASE: "@RIOTBASE@"}
                live = M.make_commands(text, mapping, sample.CC, sample.CC)
                self.assertEqual(M.compare(make_cmds(app), live), [])


@unittest.skipUnless(ARM and MAKE and CMAKE and NINJA and os.environ.get("RIOT_G3_NETWORK") == "1",
                     "needs arm-none-eabi-gcc, GNU Make, cmake, ninja and the network "
                     "(RIOT_G3_NETWORK=1); in CI: the riotbuild image, see README")
class FirmwareParityTest(unittest.TestCase):
    """P5: the same firmware with and without Make."""

    def test_same_firmware(self):
        for app, app_dir in sample.APPS.items():
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                build_dir = os.path.join(tmp, "build")
                bindirbase = os.path.join(tmp, "make-bin")
                subprocess.run(sample.make_argv(app_dir, [f"BUILD_DIR={build_dir}",
                                                          f"BINDIRBASE={bindirbase}", "-j2",
                                                          "all"]),
                               cwd=P.RIOTBASE, env=sample.environment(), check=True,
                               capture_output=True)
                builddir = os.path.join(tmp, "cmake")
                subprocess.run([sys.executable, os.path.join(TOOL, "cmake_gen.py"), "build", "-C",
                                app_dir, f"BOARD={sample.BOARD}", "-B", builddir,
                                f"BUILD_DIR={build_dir}"], cwd=P.RIOTBASE, check=True,
                               capture_output=True)
                name = plan_of(app, build_dir, builddir)["application"]
                make_out = os.path.join(bindirbase, sample.BOARD)
                for suffix in (".bin",):
                    with open(os.path.join(make_out, name + suffix), "rb") as a, \
                            open(os.path.join(builddir, name + suffix), "rb") as b:
                        self.assertEqual(a.read(), b.read(), suffix)
                for tool in (["arm-none-eabi-size", "-A"], ["arm-none-eabi-nm", "-n"]):
                    left = subprocess.run(tool + [os.path.join(make_out, name + ".elf")],
                                          capture_output=True, text=True, check=True).stdout
                    right = subprocess.run(tool + [os.path.join(builddir, name + ".elf")],
                                           capture_output=True, text=True, check=True).stdout
                    self.assertEqual(left.split("\n")[1:], right.split("\n")[1:], tool[0])


if __name__ == "__main__":
    unittest.main()
