#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RIOT contributors
# SPDX-License-Identifier: LGPL-2.1-only
"""
Generate riot-app.inc.mk from the riot-app.yaml of a RIOT application.

riot-app.yaml is the authoritative configuration of an application. It is
checked against riot-app.schema.json (JSON Schema, draft 2020-12) and turned
into a Make fragment riot-app.inc.mk next to it, which the application
Makefile includes. The fragment uses the operators of the former application
Makefile (`=`, `?=`, `+=`), so the environment and the command line still
override the values.

    riot_app_config.py examples/basic/hello-world/riot-app.yaml
    riot_app_config.py --all            # every riot-app.yaml in the repository
    riot_app_config.py --check --all    # only report outdated files

Every file needs `schema_version: 1`. Scalars are read strictly: only plain
decimal integers become numbers; other values that YAML 1.1 would turn into
numbers or booleans (017754, 0x10, 1:30, 1_000, 1.0, yes, off, ...) are
errors, so that no value changes silently. With several files (or --all) every
file is checked first; nothing is written if any of them is invalid.

Needs Python 3, PyYAML and jsonschema.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

CONFIG_NAME = "riot-app.yaml"
OUTPUT_NAME = "riot-app.inc.mk"
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
RIOTBASE = os.path.normpath(os.path.join(TOOL_DIR, "..", "..", ".."))
SCHEMA_PATH = os.path.join(TOOL_DIR, "riot-app.schema.json")
TOOL_PATH = "dist/tools/riot_app_config/riot_app_config.py"
SCHEMA_VERSION = 1
DECIMAL_INT = re.compile(r"^-?(0|[1-9][0-9]*)$")

# Simple settings: (key, Make variable, operator), in output order.
SCALARS_HEAD = [
    ("application", "APPLICATION", "="),
    ("board", "BOARD", "?="),
]
LISTS = [
    ("usemodule", "USEMODULE"),
    ("usepkg", "USEPKG"),
    ("disable_module", "DISABLE_MODULE"),
    ("features_required", "FEATURES_REQUIRED"),
    ("features_required_any", "FEATURES_REQUIRED_ANY"),
    ("features_optional", "FEATURES_OPTIONAL"),
    ("features_blacklist", "FEATURES_BLACKLIST"),
    ("cflags", "CFLAGS"),
]
SCALARS_TAIL = [
    ("develhelp", "DEVELHELP", "?="),
    ("quiet", "QUIET", "?="),
    ("werror", "WERROR", "?="),
]
DIRECTORY_LISTS = [
    ("external_board_dirs", "EXTERNAL_BOARD_DIRS"),
    ("external_module_dirs", "EXTERNAL_MODULE_DIRS"),
    ("external_pkg_dirs", "EXTERNAL_PKG_DIRS"),
]
DIRECTORY_BASES = {"riotbase": "$(RIOTBASE)", "appdir": "$(CURDIR)"}


class ConfigError(Exception):
    """A riot-app.yaml cannot be read, is invalid, or a tool is missing."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without the silent conversions of YAML 1.1.

    Duplicate keys are errors. A plain scalar becomes an integer only if it
    is written as a decimal integer; scalars that YAML 1.1 reads as numbers
    in another form (octal, hexadecimal, binary, sexagesimal, with '_', or
    floating point) and booleans (yes/no/on/off/true/false) are errors.
    """


def _where(node):
    return f"line {node.start_mark.line + 1}"


def _construct_mapping(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise ConfigError(f"duplicate key {key!r} ({_where(key_node)})")
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


def _construct_int(loader, node):
    if not DECIMAL_INT.match(node.value):
        raise ConfigError(
            f"{node.value!r} ({_where(node)}): YAML 1.1 reads this as a "
            "number in another notation (octal, hexadecimal, binary, "
            "sexagesimal or with '_'); write a plain decimal integer, or "
            "quote the value if text is meant")
    return yaml.SafeLoader.construct_yaml_int(loader, node)


def _construct_float(_loader, node):
    raise ConfigError(
        f"{node.value!r} ({_where(node)}): floating point numbers are not "
        "allowed; write a decimal integer, or quote the value if text is "
        "meant")


def _construct_bool(_loader, node):
    raise ConfigError(
        f"{node.value!r} ({_where(node)}): YAML 1.1 reads "
        "yes/no/on/off/true/false as a boolean, which riot-app.yaml does not "
        "use; write 0 or 1 for a flag, or quote the value if text is meant")


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
_StrictLoader.add_constructor("tag:yaml.org,2002:int", _construct_int)
_StrictLoader.add_constructor("tag:yaml.org,2002:float", _construct_float)
_StrictLoader.add_constructor("tag:yaml.org,2002:bool", _construct_bool)


def load_validator(schema_path=SCHEMA_PATH):
    """Return a draft 2020-12 validator for the schema; needs jsonschema."""
    try:
        import jsonschema  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ConfigError(
            "the Python module 'jsonschema' is needed to check riot-app.yaml "
            "files but is not installed (Debian/Ubuntu: package "
            "python3-jsonschema)") from exc
    try:
        with open(schema_path, encoding="utf-8") as file:
            schema = json.load(file)
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, jsonschema.SchemaError) as exc:
        raise ConfigError(f"{schema_path}: {exc}") from exc
    return jsonschema.Draft202012Validator(schema)


def load_config(path, validator):
    """Read and validate one riot-app.yaml; return the parsed data."""
    if os.path.basename(path) != CONFIG_NAME:
        raise ConfigError(f"{path}: the file must be named {CONFIG_NAME}")
    try:
        with open(path, encoding="utf-8") as file:
            config = yaml.load(file, Loader=_StrictLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    if isinstance(config, dict):
        if "schema_version" not in config:
            raise ConfigError(
                f"{path}: schema_version is missing; add "
                f"'schema_version: {SCHEMA_VERSION}'")
        if config["schema_version"] != SCHEMA_VERSION:
            raise ConfigError(
                f"{path}: schema_version {config['schema_version']!r} is not "
                f"supported; this generator reads version {SCHEMA_VERSION}")
    errors = sorted(validator.iter_errors(config),
                    key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        lines = []
        for error in errors:
            where = "/".join(str(p) for p in error.absolute_path) or "(top)"
            message = error.message
            if error.validator == "not":
                message = (f"{error.instance!r} is not allowed here (see the "
                           "key's description in riot-app.schema.json)")
            lines.append(f"{path}: {where}: {message}")
        raise ConfigError("\n".join(lines))
    return config


def render(config):
    """Return the text of riot-app.inc.mk for a validated configuration.

    schema_version is not written: it describes riot-app.yaml, not Make.
    """
    out = [
        f"# Generated from {CONFIG_NAME} by {TOOL_PATH}.",
        f"# Do not edit this file: change {CONFIG_NAME} and run",
        "# `just generate-app-config` in the root of the RIOT repository.",
    ]

    def block(lines):
        if lines:
            out.append("")
            out.extend(lines)

    block([f"{var} {op} {str(config[key])}"
           for key, var, op in SCALARS_HEAD if key in config]
          + ([f"RIOTBASE ?= $(CURDIR)/{config['riotbase']}"]
             if "riotbase" in config else []))
    for key, var in LISTS:
        block([f"{var} += {item}" for item in config.get(key, [])])
    block([f"{var} {op} {str(config[key])}"
           for key, var, op in SCALARS_TAIL if key in config])
    block([f"{name} ?= {str(value)}"
           for name, value in sorted(config.get("app_defaults", {}).items())])
    for key, var in DIRECTORY_LISTS:
        lines = []
        for entry in config.get(key, []):
            (base, path), = entry.items()
            lines.append(f"{var} += {DIRECTORY_BASES[base]}/{path}")
        block(lines)
    return "\n".join(out) + "\n"


def find_all(root=RIOTBASE):
    """Return all riot-app.yaml files in the repository (git, not ignored)."""
    try:
        result = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", f"*{CONFIG_NAME}"],
            check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfigError(f"cannot list files with git in {root}: "
                          f"{exc}") from exc
    paths = {os.path.join(root, p) for p in
             result.stdout.decode("utf-8").split("\0")
             if p and os.path.basename(p) == CONFIG_NAME}
    return sorted(p for p in paths if os.path.isfile(p))


def _write_atomic(output, text):
    """Replace output by text via a temporary file in the same directory."""
    directory = os.path.dirname(output) or "."
    try:
        mode = os.stat(output).st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                "wb", dir=directory, prefix=f".{OUTPUT_NAME}.",
                delete=False) as file:
            tmp = file.name
            file.write(text.encode("utf-8"))
        os.chmod(tmp, mode)
        os.replace(tmp, output)
    except OSError as exc:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
        raise ConfigError(f"{output}: cannot write: {exc}") from exc


def generate(path, validator):
    """Return (output path, fragment text) for one riot-app.yaml."""
    text = render(load_config(path, validator))
    return os.path.join(os.path.dirname(path), OUTPUT_NAME), text


def is_current(output, text):
    """Return None if output is missing, else whether it equals text."""
    try:
        with open(output, "rb") as file:
            return file.read() == text.encode("utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f"{output}: cannot read: {exc}") from exc


def run(paths, validator, check):
    """Check all paths, then (unless check) write the outdated fragments.

    Every error is reported; with an invalid riot-app.yaml nothing is
    written. Return the exit code.
    """
    results = []
    errors = 0
    for path in paths:
        try:
            output, text = generate(path, validator)
            results.append((output, text, is_current(output, text)))
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            errors += 1
    if errors and not check:
        print(f"error: {errors} file(s) failed; nothing written",
              file=sys.stderr)
        return 1
    for output, text, current in results:
        if current:
            continue
        if check:
            state = "missing" if current is None else "outdated"
            print(f"{output}: {state}, regenerate it from {CONFIG_NAME}",
                  file=sys.stderr)
            errors += 1
            continue
        try:
            _write_atomic(output, text)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            errors += 1
    return 1 if errors else 0


def main(argv=None):
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("configs", nargs="*", metavar=CONFIG_NAME,
                        help="configuration files to process")
    parser.add_argument("--all", action="store_true",
                        help=f"process every {CONFIG_NAME} in the repository")
    parser.add_argument("--check", action="store_true",
                        help=f"write nothing; fail if a {OUTPUT_NAME} is "
                             "missing or outdated")
    args = parser.parse_args(argv)
    if args.all == bool(args.configs):
        parser.error(f"give either --all or {CONFIG_NAME} files")
    try:
        validator = load_validator()
        configs = find_all() if args.all else args.configs
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return run(configs, validator, args.check)


if __name__ == "__main__":
    sys.exit(main())
