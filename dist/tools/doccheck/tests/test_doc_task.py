#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Unit tests for the migration of `doc` (HTML API documentation) to `just doc`.

Rules (see dist/tools/task_layer/README.md, step p3-task-layer-group1-doc):

* R1  `just doc` runs the steps `make doc` ran, in the same order, with the
      same commands, messages and exit status (feature list, GraphViz check,
      changelog, Doxygen with GENERATE_HTML/GENERATE_TAGFILE, version warning);
* R2  no recipe calls make, neither directly nor through a script it runs;
* R3  `doc` is no Make target any more (root, doc/doxygen, applications);
* R4  every caller uses `just doc`; Make targets that still need the same
      steps (`doc-man`, `doc-latex`, `doc-ci`) delegate them to just, so each
      step exists once;
* R5  the static test dist/tools/doccheck/check.sh keeps its behaviour.

Nothing is built and no repository file is changed: just is asked for its
parsed justfile and dry runs; real runs happen in a temporary copy or with
stub `just`, `doxygen`, `dot`, `make` and `uname` programs on PATH.
Doxygen is not needed.

Run: python3 -m unittest discover -s dist/tools/doccheck/tests -v
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
JUSTFILE = os.path.join(RIOTBASE, "justfile")
DOXYDIR = os.path.join(RIOTBASE, "doc", "doxygen")
APPDIR = os.path.join(RIOTBASE, "examples", "basic", "default")
JUST = shutil.which("just")
sys.path.insert(0, os.path.join(RIOTBASE, "dist", "tools", "task_layer", "tests"))

# Shared helpers of the task layer tests (same detector for R2).
import test_justfile as tl  # noqa: E402  pylint: disable=wrong-import-position

FEATURE_LIST = ("./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml "
                "--output-md doc/doxygen/src/feature_list.md")
CHANGELOG = "./generate-changelog.py src/changelog.md.tmp ../../release-notes.txt src/changelog.md"
DOXYGEN_RUN = ('( cat riot.doxyfile ; echo "GENERATE_HTML = yes" ; '
               'echo "GENERATE_TAGFILE = html/riot.tag" ) | {doxygen} -')
DOC_STEPS = ["_doc-feature-list", "_doc-graphviz-check", "_doc-changelog",
             "_doc-doxygen-version"]

# Messages as `make doc` printed them without a terminal (doc/doxygen/Makefile
# before the migration; `/usr/bin/env echo` leaves `\n` as it is).
GRAPHVIZ_ERROR = ("Error: GraphViz (dot) is not installed. "
                  "GraphViz is mandatory to generate the RIOT documentation.\n")
VERSION_WARNING = ("Warning: Doxygen version {cur} is too old. It is recommended to use "
                   "at least version 1.15.0 to avoid incorrectly formatted output.\\nYou "
                   "can use 'make doc-ci' to build the documentation with the required "
                   "Doxygen version, which will be downloaded and (if required) compiled "
                   "locally.\n")
SUCCESS = "RIOT documentation successfully generated at file://{root}/doc/doxygen/html/index.html"

# `make ... doc` as a command: make, then only options, option values, paths,
# variables or assignments, then the word doc (not doc-ci, doc/, docclean).
MAKE_DOC = re.compile(
    r"(?<![\w-])(?:g?make|\$\(MAKE\)|\$\{MAKE\})\"?"
    r"(?:\s+(?:-\S*|\"[^\"]*\"|\S*\$[({]\S*|\S*/\S*|[A-Z_][A-Z0-9_]*=\S*))*"
    r"\s+doc(?![\w./-])")

run = tl.run


def stub(bindir, name, body):
    tl.write_executable(os.path.join(bindir, name), "#!/bin/sh\n" + textwrap.dedent(body))


def env_with(bindir, **extra):
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], **extra)
    for var in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "DOXYGEN", "TAGFILE", "CC_NOCOLOR"):
        env.pop(var, None)
    return env


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.tmp.cleanup)
        self.bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bindir)
        self.log = os.path.join(self.tmp.name, "calls.log")


@unittest.skipIf(JUST is None, "just is not installed")
class DocRecipeContractTest(unittest.TestCase):
    """R1, R2: the doc recipe in the parsed justfile and its dry run."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = tl.dump(JUSTFILE)
        cls.recipes = cls.parsed["recipes"]

    def test_doc_is_public_and_its_steps_are_private(self):
        self.assertFalse(self.recipes["doc"]["private"])
        for step in DOC_STEPS:
            with self.subTest(step=step):
                self.assertTrue(self.recipes[step]["private"])

    def test_steps_run_in_make_order(self):
        doc = self.recipes["doc"]
        self.assertEqual([d["recipe"] for d in doc["dependencies"]], DOC_STEPS)
        # The version warning comes after Doxygen, as in Make.
        self.assertEqual(doc["priors"], 3)
        self.assertEqual(doc["parameters"], [])

    def test_doxygen_runs_in_doc_doxygen(self):
        for name in ("doc", "_doc-changelog"):
            with self.subTest(recipe=name):
                self.assertIn({"working-directory": "doc/doxygen"},
                              self.recipes[name]["attributes"])

    def test_dry_run_prints_the_make_commands(self):
        result = run([JUST, "--justfile", JUSTFILE, "--dry-run", "doc"],
                     env=env_with(os.devnull))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stderr.splitlines()
        order = [lines.index(FEATURE_LIST),
                 lines.index("command -v dot >/dev/null 2>&1 || {"),
                 lines.index(CHANGELOG),
                 lines.index(DOXYGEN_RUN.format(doxygen="doxygen")),
                 lines.index('echo "' + SUCCESS.format(root=RIOTBASE) + '"'),
                 lines.index("cur=$(doxygen --version | cut -d ' ' -f1)")]
        self.assertEqual(order, sorted(order))

    def test_doxygen_and_tagfile_like_make_variables(self):
        cases = {
            "environment": ({"DOXYGEN": "/opt/dx", "TAGFILE": "t.tag"}, []),
            "command line": ({}, ["DOXYGEN=/opt/dx", "TAGFILE=t.tag"]),
        }
        for how, (extra_env, overrides) in cases.items():
            with self.subTest(how=how):
                result = run([JUST, "--justfile", JUSTFILE, "--dry-run"] + overrides + ["doc"],
                             env=dict(env_with(os.devnull), **extra_env))
                self.assertIn('echo "GENERATE_TAGFILE = t.tag" ) | /opt/dx -', result.stderr)
                self.assertIn("cur=$(/opt/dx --version", result.stderr)

    def test_no_recipe_calls_make(self):
        self.assertEqual(tl.recipes_calling_make(self.parsed), [])

    def test_scripts_run_by_doc_start_no_process(self):
        # R2 "via a script": the two Python generators only read and write files.
        for script in ("dist/tools/features_yaml2mx/features_yaml2mx.py",
                       "doc/doxygen/generate-changelog.py"):
            with self.subTest(script=script):
                with open(os.path.join(RIOTBASE, script), encoding="utf-8") as file:
                    text = file.read()
                self.assertIsNone(re.search(r"subprocess|os\.system|os\.popen|os\.exec", text))

    def test_min_version_defined_once_and_read_by_make(self):
        just_value = run([JUST, "--justfile", JUSTFILE, "--evaluate", "doxygen_min_version"])
        make_value = run(["make", "-s", "--no-print-directory", "-C", DOXYDIR, "--eval",
                          "print-min:\n\t@echo $(DOXYGEN_MIN_VERSION)", "print-min"])
        self.assertEqual(make_value.stdout.strip(), just_value.stdout.strip())
        self.assertRegex(just_value.stdout, r"^\d+\.\d+\.\d+$")
        with open(os.path.join(DOXYDIR, "Makefile"), encoding="utf-8") as file:
            self.assertNotRegex(file.read(), r"DOXYGEN_MIN_VERSION\s*:?=\s*\d")


@unittest.skipIf(JUST is None, "just is not installed")
class CheckRecipesTest(TempDirTest):
    """R1: GraphViz check and version warning keep messages and exit status."""

    def just(self, *args, path):
        return run([JUST, "--justfile", JUSTFILE, *args], env=dict(env_with(os.devnull), PATH=path))

    def test_graphviz_missing_fails_with_make_message(self):
        # PATH with echo (Make's COLOR_ECHO is `/usr/bin/env echo`) but no dot.
        os.symlink(shutil.which("echo"), os.path.join(self.bindir, "echo"))
        result = self.just("_doc-graphviz-check", path=self.bindir)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, GRAPHVIZ_ERROR)

    def test_graphviz_present_passes_silently(self):
        stub(self.bindir, "dot", "exit 0\n")
        result = self.just("_doc-graphviz-check", path=self.bindir)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_version_warning(self):
        cases = {"1.9.1": True, "1.14.9": True, "1.15.0": False, "1.15.0 (abc123)": False,
                 "1.16.1": False, "2.0.0": False}
        for version, warns in cases.items():
            with self.subTest(version=version):
                stub(self.bindir, "doxygen", f'echo "{version}"\n')
                path = self.bindir + os.pathsep + os.environ["PATH"]
                result = self.just("_doc-doxygen-version", path=path)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = VERSION_WARNING.format(cur=version.split()[0]) if warns else ""
                self.assertEqual(result.stdout, expected)


@unittest.skipIf(JUST is None, "just is not installed")
class DocRunInTemporaryTreeTest(TempDirTest):
    """R1: `just doc` in a copy of the needed files, with stub doxygen and dot."""

    FILES = ("justfile", "features.yaml", "release-notes.txt",
             "dist/tools/features_yaml2mx/features_yaml2mx.py",
             "doc/doxygen/generate-changelog.py", "doc/doxygen/riot.doxyfile",
             "doc/doxygen/src/changelog.md.tmp")

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp.name, "riot")
        for path in self.FILES:
            os.makedirs(os.path.join(self.root, os.path.dirname(path)), exist_ok=True)
            shutil.copy2(os.path.join(RIOTBASE, path), os.path.join(self.root, path))
        stub(self.bindir, "dot", "exit 0\n")
        stub(self.bindir, "doxygen", f"""\
            if [ "$1" = --version ]; then echo 1.15.0; exit 0; fi
            pwd > "{self.log}"
            cat > "{self.log}.stdin"
            exit "${{DOXYGEN_EXIT:-0}}"
            """)

    def just_doc(self, **extra):
        return run([JUST, "--justfile", os.path.join(self.root, "justfile"), "doc"],
                   env=env_with(self.bindir, **extra), cwd=self.tmp.name)

    def test_builds_inputs_and_runs_doxygen_in_doc_doxygen(self):
        result = self.just_doc()
        self.assertEqual(result.returncode, 0, result.stderr)
        doxydir = os.path.join(self.root, "doc", "doxygen")
        with open(self.log, encoding="utf-8") as file:
            self.assertEqual(os.path.realpath(file.read().strip()), os.path.realpath(doxydir))
        with open(os.path.join(doxydir, "riot.doxyfile"), encoding="utf-8") as file:
            expected = file.read() + "GENERATE_HTML = yes\nGENERATE_TAGFILE = html/riot.tag\n"
        with open(self.log + ".stdin", encoding="utf-8") as file:
            self.assertEqual(file.read(), expected)
        for generated in ("feature_list.md", "changelog.md"):
            with self.subTest(generated=generated):
                self.assertGreater(os.path.getsize(os.path.join(doxydir, "src", generated)), 0)
        self.assertEqual(result.stdout, "\n" + SUCCESS.format(root=self.root) + "\n")

    def test_doxygen_failure_fails_and_skips_the_rest(self):
        result = self.just_doc(DOXYGEN_EXIT="3")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("successfully generated", result.stdout)

    def test_missing_dot_stops_before_doxygen(self):
        os.remove(os.path.join(self.bindir, "dot"))
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(bare)
        for tool in ("python3", "cut", "sort", "head", "cat", "echo"):
            os.symlink(shutil.which(tool), os.path.join(bare, tool))
        result = run([JUST, "--justfile", os.path.join(self.root, "justfile"), "doc"],
                     env=dict(env_with(self.bindir), PATH=self.bindir + os.pathsep + bare))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("GraphViz (dot) is not installed", result.stdout)
        self.assertFalse(os.path.exists(self.log))


class MakeNoLongerKnowsDocTest(unittest.TestCase):
    """R3: `make doc` fails as an unknown target everywhere."""

    def test_root(self):
        result = run(["make", "--no-print-directory", "-n", "doc"], cwd=RIOTBASE)
        self.assertIn('unrecognized target "doc"', result.stdout)
        self.assertNotIn("features_yaml2mx", result.stdout)
        result = run(["make", "--no-print-directory", "doc"], cwd=RIOTBASE)
        self.assertNotEqual(result.returncode, 0)

    def test_doc_doxygen(self):
        for target in ("doc", "html"):
            with self.subTest(target=target):
                result = run(["make", "--no-print-directory", "-n", "-C", DOXYDIR, target])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"No rule to make target '{target}'", result.stderr)

    def test_application(self):
        result = run(["make", "--no-print-directory", "-n", "doc"], cwd=APPDIR)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No rule to make target 'doc'", result.stderr)

    def test_no_rule_or_phony_entry(self):
        for name in ("Makefile.include", "doc/doxygen/Makefile"):
            with self.subTest(makefile=name):
                with open(os.path.join(RIOTBASE, name), encoding="utf-8") as file:
                    text = file.read()
                self.assertIsNone(re.search(r"^(\S+ )*doc( \S+)*\s*:", text, re.M))
                phony = " ".join(re.findall(r"^\.PHONY:(.*)$", text, re.M)).split()
                self.assertNotIn("doc", phony)
                self.assertNotIn("GENERATE_HTML", text)

    def test_welcome_text_lists_doc_under_just(self):
        with open(os.path.join(RIOTBASE, "Makefile"), encoding="utf-8") as file:
            text = file.read()
        moved = text.split("moved to just (run", 1)[1].splitlines()[1]
        self.assertIn(" doc ", moved + " ")
        before = text.split("moved to just (run", 1)[0]
        self.assertNotRegex(before, r'@echo " doc[ "]')


class DetectorTest(unittest.TestCase):
    """The `make ... doc` detector used for R4 (positive and negative samples)."""

    def test_detects_calls(self):
        for line in ("make doc", 'make -C "${RIOTBASE}" doc 2>&1)',
                     "$(MAKE) -C $(RIOTBASE) doc", "@$(MAKE) -BC $(CURDIR) DOXYGEN=x doc",
                     "calling `make doc` and then", '"$(MAKE)" -C doc/doxygen doc',
                     "make BOARD=native doc", "gmake doc"):
            with self.subTest(line=line):
                self.assertRegex(line, MAKE_DOC)

    def test_ignores_other_targets_and_prose(self):
        for line in ("make doc-ci", "make doc-man", "make -C doc/doxygen clean",
                     "Execute `make doc-ci` instead of `just doc`", "make sure the doc is",
                     "just doc", "make docclean", "[gnumake doc](https://x)", "cmake doc",
                     "make -C doc/starlight dev"):
            with self.subTest(line=line):
                self.assertNotRegex(line, MAKE_DOC)


class CallerTest(unittest.TestCase):
    """R4: no caller runs `make doc`; doccheck and the guides use just."""

    # Name `make doc` on purpose: history, the migration docs and these tests.
    DOCUMENTS_THE_MIGRATION = ("release-notes.txt", "dist/tools/task_layer",
                               "dist/tools/doccheck/tests")

    def test_no_caller_runs_make_doc(self):
        excludes = [f":(exclude){path}" for path in self.DOCUMENTS_THE_MIGRATION]
        result = run(["git", "grep", "--untracked", "-n", "-i", "-e", "make", "--and",
                      "-e", "doc", "--", "."] + excludes, cwd=RIOTBASE)
        if result.returncode == 128:
            self.skipTest("not a git checkout: " + result.stderr.strip())
        hits = [line for line in result.stdout.splitlines() if MAKE_DOC.search(line)]
        self.assertEqual(hits, [], "still calls make for doc")

    def test_guides_name_just_doc(self):
        for path in ("doc/guides/advanced_tutorials/porting_boards.mdx",
                     "doc/guides/general/structure.mdx", "doc/starlight/README.md",
                     "doc/starlight/src/lib/doxygen_docs.ts"):
            with self.subTest(path=path):
                with open(os.path.join(RIOTBASE, path), encoding="utf-8") as file:
                    self.assertIn("`just doc`", file.read())

    def test_static_tests_require_just_for_doccheck(self):
        with open(os.path.join(RIOTBASE, "dist/tools/ci/static_tests.sh"), encoding="utf-8") as f:
            deps = re.search(r'DEPS\["\./dist/tools/doccheck/check\.sh"\]="([^"]*)"', f.read())
        self.assertIn("just", deps.group(1).split())


class MakeDelegatesToJustTest(TempDirTest):
    """R4: doc-man, doc-latex and doc-ci run the shared steps with just."""

    def setUp(self):
        super().setUp()
        self.just = os.path.join(self.bindir, "just")
        stub(self.bindir, "just", f'echo "$*" >> "{self.log}"\n')
        self.doxygen = os.path.join(self.bindir, "doxygen")
        stub(self.bindir, "doxygen", "cat > /dev/null\n")

    def calls(self):
        with open(self.log, encoding="utf-8") as file:
            return file.read().splitlines()

    def test_doc_man_and_doc_latex(self):
        for target in ("doc-man", "doc-latex"):
            with self.subTest(target=target):
                if os.path.exists(self.log):
                    os.remove(self.log)
                # Make itself decides whether the changelog is out of date.
                stale = run(["make", "-q", "-C", DOXYDIR, "src/changelog.md"]).returncode != 0
                result = run(["make", "--no-print-directory", target,
                              f"JUST={self.just}", f"DOXYGEN={self.doxygen}"],
                             cwd=RIOTBASE, env=env_with(self.bindir))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                prefix = f"--justfile {JUSTFILE} "
                expected = [prefix + "_doc-feature-list", prefix + "_doc-graphviz-check"]
                expected += [prefix + "_doc-changelog"] if stale else []
                expected += [prefix + f"DOXYGEN={self.doxygen} _doc-doxygen-version"]
                self.assertEqual(self.calls(), expected)

    def test_failing_check_stops_make(self):
        stub(self.bindir, "just", "case \"$*\" in *graphviz*) exit 1;; esac\n")
        result = run(["make", "--no-print-directory", "-C", DOXYDIR, "doc-man",
                      f"JUST={self.just}", f"DOXYGEN={self.doxygen}"], env=env_with(self.bindir))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("successfully generated", result.stdout)

    def test_doc_ci_runs_just_doc_with_downloaded_doxygen(self):
        result = run(["make", "--no-print-directory", "-n", "-C", DOXYDIR, "doc-ci"],
                     env=env_with(self.bindir))
        self.assertEqual(result.returncode, 0, result.stderr)
        doxygen = os.path.join(RIOTBASE, "dist", "tools", "doxygen", "doxygen")
        self.assertEqual(result.stdout.splitlines()[-1],
                         f'"just" --justfile "{JUSTFILE}" DOXYGEN="{doxygen}" doc')

    def test_root_doc_ci_goes_to_doc_doxygen(self):
        result = run(["make", "--no-print-directory", "-n", "doc-ci"], cwd=RIOTBASE,
                     env=env_with(self.bindir))
        self.assertIn('"make" -C doc/doxygen doc-ci', result.stdout.splitlines()[0])

    def test_application_forwards_doc_man_to_root(self):
        result = run(["make", "--no-print-directory", "-n", "doc-man"], cwd=APPDIR,
                     env=env_with(self.bindir))
        self.assertIn(f"-C {RIOTBASE} doc-man", result.stdout)


class DoccheckScriptTest(TempDirTest):
    """R5: dist/tools/doccheck/check.sh in a temporary tree with stubs."""

    FILES = ("dist/tools/doccheck/check.sh", "dist/tools/doccheck/exclude_simple",
             "dist/tools/doccheck/exclude_patterns",
             "dist/tools/doccheck/generic_exclude_patterns",
             "dist/tools/ci/github_annotate.sh")
    OK_OUTPUT = 'echo "RIOT documentation successfully generated at file:///x/index.html"'

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp.name, "riot")
        for path in self.FILES:
            os.makedirs(os.path.join(self.root, os.path.dirname(path)), exist_ok=True)
            shutil.copy2(os.path.join(RIOTBASE, path), os.path.join(self.root, path))
        run(["git", "init", "-q", self.root])
        self.machine("Linux aarch64")

    def machine(self, text):
        stub(self.bindir, "uname", f'echo "{text}"\n')

    def tool(self, name, output):
        stub(self.bindir, name, f'echo "{name} $*" >> "{self.log}"\n{output}\n')

    def check(self):
        env = env_with(self.bindir)
        env.pop("GITHUB_RUN_ID", None)
        return run(["bash", os.path.join(self.root, "dist", "tools", "doccheck", "check.sh")],
                   env=env, cwd=self.root)

    def logged(self):
        with open(self.log, encoding="utf-8") as file:
            return file.read().splitlines()

    def test_clean_build_passes_and_runs_just_doc(self):
        self.tool("just", self.OK_OUTPUT)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.logged(), [f"just --justfile {self.root}/justfile doc"])

    def test_doxygen_warning_fails(self):
        self.tool("just", self.OK_OUTPUT + '\necho "sys/foo.h:12: warning: bad thing"')
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Doxygen generates the following warnings", result.stdout)
        self.assertIn("sys/foo.h:12: warning: bad thing", result.stdout)

    def test_excluded_warning_passes(self):
        self.tool("just", self.OK_OUTPUT + '\necho "b.h:1: warning: Member UART_NUMOF '
                  '(macro definition) of file b.h is not documented."')
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_judges_the_output_not_the_exit_status(self):
        # Unchanged behaviour: DOXY_ERRCODE is the status of the grep filter,
        # so a failing build without warnings passes, as with `make doc`.
        self.tool("just", "exit 1")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("exited with non-zero code", result.stdout)

    def test_linux_x86_64_uses_make_doc_ci(self):
        self.machine("Linux x86_64")
        self.tool("make", self.OK_OUTPUT)
        self.tool("just", "exit 99")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.logged(), [f"make -C {self.root} doc-ci"])


@unittest.skipIf(JUST is None, "just is not installed")
class ReachabilityTest(unittest.TestCase):
    """R6 (decision 2026-11-20): `just doc` may be called from any directory of
    the repository. Make offered `doc` at the root and (by delegation to the
    root) in applications; the result never depended on the directory. Checked:
    same command list from every directory, recipe runs in the repository root."""

    DIRECTORIES = (".", "examples/basic/hello-world", "boards", "sys", "doc/doxygen")

    def test_same_commands_from_every_directory(self):
        outputs = set()
        for directory in self.DIRECTORIES:
            with self.subTest(directory=directory):
                result = subprocess.run([JUST, "--dry-run", "doc"], cwd=os.path.join(RIOTBASE, directory),
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.add(result.stderr)
        self.assertEqual(len(outputs), 1)

    def test_recipe_runs_in_the_repository_root(self):
        result = subprocess.run([JUST, "--justfile", os.path.join(RIOTBASE, "justfile"), "--dump",
                                 "--dump-format", "json"], capture_output=True, text=True, check=True)
        import json  # pylint: disable=import-outside-toplevel
        self.assertNotIn("no-cd", json.loads(result.stdout)["recipes"]["doc"]["attributes"])


if __name__ == "__main__":
    unittest.main()
