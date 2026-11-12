# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
#
# Documentation: Doxygen (doc/doxygen) and the Starlight site (doc/starlight).
# Imported by the root justfile; settings in just/settings.just. Recipes from
# doc/doxygen and doc/starlight are named `doxygen-<step>` and
# `starlight-<step>`, so that generic names such as `build`, `check` or
# `security` stay unambiguous; `doxygen-version` and `graphviz-check` keep
# their names.

# Generate the HTML documentation with Doxygen.
[group('doc')]
doc: _doc-feature-list doxygen-doc

# Generate man pages with Doxygen.
[group('doc')]
doc-man: _doc-feature-list doxygen-doc-man

# Generate LaTeX documentation with Doxygen.
[group('doc')]
doc-latex: _doc-feature-list doxygen-doc-latex

# Build and serve the Starlight documentation site.
[group('doc')]
doc-starlight: starlight-dev

# doc/doxygen/src/feature_list.md from features.yaml.
[private]
_doc-feature-list:
    @./dist/tools/features_yaml2mx/features_yaml2mx.py features.yaml --output-md doc/doxygen/src/feature_list.md

# ---------------------------------------------------------------- doc/doxygen

# HTML documentation: check Graphviz, run Doxygen, check the Doxygen version.
[group('doc')]
doxygen-doc: (_doxygen-steps "graphviz-check" if DOCUMENTATION_FORMAT == "(derived)" { "html" } else { DOCUMENTATION_FORMAT } "doxygen-version")

# Man pages: check Graphviz, run Doxygen, check the Doxygen version.
[group('doc')]
doxygen-doc-man: (_doxygen-steps "graphviz-check" if DOCUMENTATION_FORMAT == "(derived)" { "man" } else { DOCUMENTATION_FORMAT } "doxygen-version")

# LaTeX documentation: check Graphviz, run Doxygen, check the Doxygen version.
[group('doc')]
doxygen-doc-latex: (_doxygen-steps "graphviz-check" if DOCUMENTATION_FORMAT == "(derived)" { "latex" } else { DOCUMENTATION_FORMAT } "doxygen-version")

# Run Doxygen and generate HTML (doc/doxygen/html).
[group('doc')]
doxygen-html: (_doxygen-steps "html")

# Run Doxygen and generate man pages (doc/doxygen/man).
[group('doc')]
doxygen-man: (_doxygen-steps "man")

# Run Doxygen and generate LaTeX (doc/doxygen/latex).
[group('doc')]
doxygen-latex: (_doxygen-steps "latex")

# Run Doxygen without an output format to report documentation warnings.
[group('doc')]
doxygen-check: (_doxygen-steps "check")

# Warn when the installed Doxygen is older than DOXYGEN_MIN_VERSION.
[group('doc')]
doxygen-version: (_doxygen-steps "doxygen-version")

# Fail when Graphviz (`dot`), which Doxygen needs, is not installed.
[group('doc')]
graphviz-check: (_doxygen-steps "graphviz-check")

# Runs the given Doxygen steps in order, each once: graphviz-check,
# doxygen-version, and the Doxygen outputs html, man, latex and check. A step
# argument may hold several words (DOCUMENTATION_FORMAT="html man"); an empty
# one is skipped. Steps arrive as arguments, never as script text.
[no-exit-message]
[positional-arguments]
[private]
[working-directory('doc/doxygen')]
_doxygen-steps *steps:
    #!/usr/bin/env bash
    {{ _colors }}
    set -f
    # Default RIOTBASE: the git top level; outside a git checkout it stays
    # empty and Doxygen still runs.
    riotbase="$_RIOT_DOC_RIOTBASE"
    if [ "$riotbase" = "(git top level)" ]; then
        riotbase=$(git rev-parse --show-toplevel || true)
    fi
    doxygen="$_RIOT_DOXYGEN"
    min="$_RIOT_DOXYGEN_MIN_VERSION"

    graphviz_check() {
        command -v dot >/dev/null 2>&1 || {
            $color_echo "${color_red}Error: GraphViz (dot) is not installed." \
              "GraphViz is mandatory to generate the RIOT documentation.${color_reset}"
            return 1
        }
    }

    doxygen_version() {
        local cur
        cur=$(/bin/sh -c "$doxygen --version | cut -d ' ' -f1")
        if [ "`{ echo "$min"; echo "$cur"; } | sort -V | head -n1`" != "$min" ]; then
            $color_echo "${color_red}Warning: Doxygen version $cur is too old." \
              "It is recommended to use at least version $min" \
              "to avoid incorrectly formatted output.\nYou can use 'make doc-ci' to build" \
              "the documentation with the required Doxygen version, which will be downloaded" \
              "and (if required) compiled locally.${color_reset}"
        fi
    }

    # src/changelog.md from the template and release-notes.txt: both inputs
    # must exist; the file is regenerated when one of them is newer.
    changelog() {
        local input
        for input in src/changelog.md.tmp ../../release-notes.txt; do
            if [ ! -e "$input" ]; then
                echo "error: $input is missing (needed by src/changelog.md)" >&2
                return 2
            fi
        done
        if [ ! -e src/changelog.md ] || [ src/changelog.md.tmp -nt src/changelog.md ] || \
           [ ../../release-notes.txt -nt src/changelog.md ]; then
            ./generate-changelog.py src/changelog.md.tmp ../../release-notes.txt src/changelog.md
        fi
    }

    run_doxygen() {
        local cmd out include_paths
        changelog || return
        # Quoted absolute include paths, in Doxygen's environment as
        # STRIP_FROM_INC_PATH_LIST.
        include_paths=$(git ls-tree -dr --full-tree --name-only HEAD core drivers sys | \
            grep '/include$' | \
            sed "s/.*/\"${riotbase//\//\\/}\/\0\"/" | \
            paste -sd ' ')
        case $1 in
            html)  cmd='( cat riot.doxyfile ; echo "GENERATE_HTML = yes" ) | '"$doxygen"' -'
                   out=html/index.html ;;
            man)   cmd='( cat riot.doxyfile ; echo "GENERATE_MAN = yes" ) | '"$doxygen"' -'
                   out=man/man3 ;;
            latex) cmd='( cat riot.doxyfile ; echo "GENERATE_LATEX= yes" ) | '"$doxygen"' -'
                   out=latex/index.tex ;;
            check) cmd='( cat riot.doxyfile) | '"$doxygen"' -'
                   out= ;;
        esac
        # The command line is printed before it runs.
        printf '%s\n' "$cmd"
        STRIP_FROM_INC_PATH_LIST=$include_paths /bin/sh -c "$cmd" || return
        if [ -n "$out" ]; then
            echo ""
            echo "RIOT documentation successfully generated at file://$riotbase/doc/doxygen/$out"
        fi
    }

    done_steps=" "
    for arg in "$@"; do
        for step in $arg; do
            case $done_steps in *" $step "*) continue ;; esac
            done_steps+="$step "
            case $step in
                graphviz-check) graphviz_check ;;
                doxygen-version) doxygen_version ;;
                html|man|latex|check) run_doxygen "$step" ;;
                *) echo "error: no Doxygen step '$step'" >&2; exit 2 ;;
            esac || exit
        done
    done

# ---------------------------------------------------------------- doc/starlight
#
# The copy recipes fail when their Markdown source is missing; errors of the
# copy lines themselves are ignored (`-`), as before.

# Build the Starlight documentation site (doc/starlight/dist).
[group('doc')]
starlight-build: starlight-install _starlight-build-step

# Build the Starlight site and serve the result locally.
[group('doc')]
starlight-preview: starlight-build _starlight-preview-step

# Serve the Starlight site with live reload.
[group('doc')]
starlight-dev: starlight-install _starlight-dev-step

# Also run by `make -C doc/starlight install`.
[doc("Install the site's npm dependencies (doc/starlight/node_modules).")]
[group('doc')]
[working-directory('doc/starlight')]
starlight-install: starlight-integrate_outside_files
    @echo "Installing starlight..."
    @npm ci --prefix "$(pwd -P)" --prefer-offline --no-fund --no-audit
    @echo "\nStarlight installed successfully."

[private]
[working-directory('doc/starlight')]
_starlight-build-step:
    #!/bin/sh
    npm run build --prefix "$(pwd -P)" || exit
    riotbase="$_RIOT_DOC_RIOTBASE"
    if [ "$riotbase" = "(git top level)" ]; then
        riotbase=$(git rev-parse --show-toplevel)
    fi
    echo "RIOT documentation successfully generated at file://$riotbase/doc/starlight/dist/index.html"

[private]
[working-directory('doc/starlight')]
_starlight-preview-step:
    @npm run preview --prefix "$(pwd -P)"

[private]
[working-directory('doc/starlight')]
_starlight-dev-step:
    @echo "Starting starlight live server..."
    @npm run dev --prefix "$(pwd -P)"

# Copy the repository Markdown documents into the Starlight guides.
[group('doc')]
starlight-integrate_outside_files: starlight-code_of_conduct starlight-governance starlight-lostandfound starlight-coding_conventions starlight-coding_conventions_cpp starlight-security starlight-unittests starlight-contributing

# Generate doc/guides/generated/CODE_OF_CONDUCT.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-code_of_conduct:
    @[ -e ../../CODE_OF_CONDUCT.md ] || { echo "error: ../../CODE_OF_CONDUCT.md is missing (needed by starlight-code_of_conduct)" >&2; exit 2; }
    -@mkdir -p ../guides/generated
    -@echo "Generating Code of Conduct documentation..."
    -@sed '1,2d' ../../CODE_OF_CONDUCT.md | cat ./templates/CODE_OF_CONDUCT.template.md - > ../guides/generated/CODE_OF_CONDUCT.md

# Generate doc/guides/generated/GOVERNANCE.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-governance:
    @[ -e ../../GOVERNANCE.md ] || { echo "error: ../../GOVERNANCE.md is missing (needed by starlight-governance)" >&2; exit 2; }
    -@echo "Generating Governance documentation..."
    -@sed '1,2d' ../../GOVERNANCE.md | sed '/<!-- TOC start -->/,/<!-- TOC end -->/d' | cat ./templates/GOVERNANCE.template.md - > ../guides/generated/GOVERNANCE.md

# Generate doc/guides/generated/LOSTANDFOUND.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-lostandfound:
    @[ -e ../../LOSTANDFOUND.md ] || { echo "error: ../../LOSTANDFOUND.md is missing (needed by starlight-lostandfound)" >&2; exit 2; }
    -@echo "Generating Lost and Found documentation..."
    -@sed '1,2d' ../../LOSTANDFOUND.md | cat ./templates/LOSTANDFOUND.template.md - > ../guides/generated/LOSTANDFOUND.md

# Generate doc/guides/generated/CODING_CONVENTIONS.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-coding_conventions:
    @[ -e ../../CODING_CONVENTIONS.md ] || { echo "error: ../../CODING_CONVENTIONS.md is missing (needed by starlight-coding_conventions)" >&2; exit 2; }
    -@echo "Generating Coding Conventions documentation..."
    -@sed '1,2d' ../../CODING_CONVENTIONS.md | cat ./templates/CODING_CONVENTIONS.template.md - > ../guides/generated/CODING_CONVENTIONS.md

# Generate doc/guides/generated/CODING_CONVENTIONS_CPP.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-coding_conventions_cpp:
    @[ -e ../../CODING_CONVENTIONS_C++.md ] || { echo "error: ../../CODING_CONVENTIONS_C++.md is missing (needed by starlight-coding_conventions_cpp)" >&2; exit 2; }
    -@echo "Generating C++ Coding Conventions documentation..."
    -@sed '1,2d' ../../CODING_CONVENTIONS_C++.md | cat ./templates/CODING_CONVENTIONS_CPP.template.md - > ../guides/generated/CODING_CONVENTIONS_CPP.md

# Generate doc/guides/generated/SECURITY.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-security:
    @[ -e ../../SECURITY.md ] || { echo "error: ../../SECURITY.md is missing (needed by starlight-security)" >&2; exit 2; }
    -@mkdir -p ../guides/generated
    -@echo "Generating Security Guidelines..."
    -@sed '1,2d' ../../SECURITY.md | cat ./templates/SECURITY.template.md - > ../guides/generated/SECURITY.md

# Generate doc/guides/generated/tests/unittests/README.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-unittests:
    @[ -e ../../tests/unittests/README.md ] || { echo "error: ../../tests/unittests/README.md is missing (needed by starlight-unittests)" >&2; exit 2; }
    -@echo "Generating Unittests documentation..."
    -@mkdir -p ../guides/generated/tests/unittests
    -@sed '1,2d' ../../tests/unittests/README.md | cat ./templates/UNITTESTS.template.md - > ../guides/generated/tests/unittests/README.md

# Generate doc/guides/generated/CONTRIBUTING.md.
[group('doc')]
[working-directory('doc/starlight')]
starlight-contributing:
    @[ -e ../../CONTRIBUTING.md ] || { echo "error: ../../CONTRIBUTING.md is missing (needed by starlight-contributing)" >&2; exit 2; }
    -@echo "Generating Contributing documentation..."
    -@mkdir -p ../guides/generated
    -@sed '1,2d' ../../CONTRIBUTING.md | cat ./templates/CONTRIBUTING.template.md - > ../guides/generated/CONTRIBUTING.md
