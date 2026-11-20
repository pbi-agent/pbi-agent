from __future__ import annotations

import argparse
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import pytest

from pbi_agent import cli
from pbi_agent.cli import entrypoint as cli_entrypoint
from pbi_agent.cli import parser as cli_parser
from pbi_agent.cli.doc import (
    DOC_HELP,
    ROOT_DOC_HELP,
    DocAction,
    attach_doc_options,
    guide_filename,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDES_DIR = files("pbi_agent.cli").joinpath("guides")

CommandPath = tuple[str, ...]


def _subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action  # pyright: ignore[reportUnknownVariableType]
    return None


def _walk(
    parser: argparse.ArgumentParser,
) -> list[tuple[CommandPath, argparse.ArgumentParser]]:
    """Independent tree walk (does not reuse ``iter_parser_paths``)."""
    found: list[tuple[CommandPath, argparse.ArgumentParser]] = []
    seen: set[int] = set()

    def visit(path: CommandPath, current: argparse.ArgumentParser) -> None:
        seen.add(id(current))
        found.append((path, current))
        action = _subparsers_action(current)
        if action is None:
            return
        for name, child in action.choices.items():
            if id(child) not in seen:
                visit((*path, name), child)

    visit((), parser)
    return found


def _children(parser: argparse.ArgumentParser) -> list[str]:
    action = _subparsers_action(parser)
    if action is None:
        return []
    names: list[str] = []
    seen: set[int] = set()
    for name, child in action.choices.items():
        if id(child) not in seen:
            seen.add(id(child))
            names.append(name)
    return names


def _guide_text(path: CommandPath) -> str | None:
    resource = GUIDES_DIR.joinpath(guide_filename(path))
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


def _paths_without_guides(parser: argparse.ArgumentParser) -> list[CommandPath]:
    return [path for path, _ in _walk(parser) if _guide_text(path) is None]


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines)
            current = line[3:].strip()
            lines = []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines)
    return sections


def _code_blocks(text: str, language: str) -> list[str]:
    return re.findall(rf"^```{language}\n(.*?)^```", text, flags=re.S | re.M)


def _backtick_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for span in re.findall(r"`([^`\n]+)`", text):
        tokens.update(token for token in re.split(r"[ ,=]+", span) if token)
    return tokens


def _command_label(path: CommandPath) -> str:
    return " ".join(("pbi-agent", *path))


PARSER = cli.build_parser()
WALK = _walk(PARSER)
EXPECTED_PATHS: list[CommandPath] = [path for path, _ in WALK]
PARSERS_BY_PATH = dict(WALK)
PARENT_PATHS = [
    path for path in EXPECTED_PATHS if path and _children(PARSERS_BY_PATH[path])
]
LEAF_PATHS = [path for path in EXPECTED_PATHS if path and path not in PARENT_PATHS]
PATH_IDS = [_command_label(path) for path in EXPECTED_PATHS]

LEAF_SECTIONS = [
    "Purpose",
    "Usage",
    "Options and arguments",
    "Examples",
    "Workflows",
    "Related commands",
    "Pitfalls",
]
PARENT_SECTIONS = [*LEAF_SECTIONS[:2], "Subcommands", *LEAF_SECTIONS[2:]]
ROOT_SECTIONS = [
    "Overview",
    "Usage",
    "Global options",
    "Settings resolution",
    "Commands",
    "Examples",
    "Getting more detail",
    "Pitfalls",
]
SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "2>&1", "&"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@pytest.fixture
def wide_terminal():
    with patch.object(
        shutil, "get_terminal_size", return_value=os.terminal_size((120, 24))
    ):
        yield


@pytest.fixture
def no_maintenance():
    with patch.object(
        cli_entrypoint,
        "run_startup_maintenance",
        side_effect=AssertionError("maintenance must not run for --doc"),
    ):
        yield


def _run_main(argv: list[str]) -> tuple[int | str | None, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
        pytest.raises(SystemExit) as exc_info,
    ):
        cli.main(argv)
    return exc_info.value.code, stdout.getvalue(), stderr.getvalue()


def test_tree_has_expected_paths() -> None:
    assert len(EXPECTED_PATHS) == 56
    assert EXPECTED_PATHS[0] == ()
    assert ("config", "providers", "create") in EXPECTED_PATHS
    assert ("channels", "telegram", "configure") in EXPECTED_PATHS
    assert ("upgrade",) in EXPECTED_PATHS
    assert ("update",) not in EXPECTED_PATHS


def test_every_parser_has_one_doc_action() -> None:
    for path, parser in WALK:
        doc_actions = [
            action for action in parser._actions if isinstance(action, DocAction)
        ]
        assert len(doc_actions) == 1, path
        assert doc_actions[0].option_strings == ["--doc"], path
        assert doc_actions[0].guide_path == path
        assert doc_actions[0].help == (DOC_HELP if path else ROOT_DOC_HELP)


def test_every_path_has_guide() -> None:
    assert _paths_without_guides(PARSER) == []


def test_no_orphan_guides() -> None:
    guide_names = {
        entry.name for entry in GUIDES_DIR.iterdir() if entry.name.endswith(".md")
    }
    assert guide_names == {guide_filename(path) for path in EXPECTED_PATHS}


def test_guard_flags_new_subparser_without_guide() -> None:
    with patch.object(cli_parser, "attach_doc_options"):
        parser = cli_parser.build_parser()
    action = _subparsers_action(parser)
    assert action is not None
    action.add_parser("zz-undocumented", prog="pbi-agent zz-undocumented")
    attach_doc_options(parser)

    assert _paths_without_guides(parser) == [("zz-undocumented",)]

    stderr = io.StringIO()
    with patch("sys.stderr", stderr), pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["zz-undocumented", "--doc"])
    assert exc_info.value.code == 1
    assert "no --doc guide found for `pbi-agent zz-undocumented`" in stderr.getvalue()


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_doc_prints_guide_and_exits_zero(path: CommandPath, no_maintenance) -> None:
    code, stdout, stderr = _run_main([*path, "--doc"])

    guide = _guide_text(path)
    assert guide is not None
    assert code == 0
    assert stdout == guide.rstrip("\n") + "\n"
    assert stdout.strip()
    assert stdout.startswith("# pbi-agent")
    assert stderr == ""


def test_update_alias_prints_upgrade_guide(no_maintenance) -> None:
    code, stdout, _ = _run_main(["update", "--doc"])

    assert code == 0
    assert stdout.startswith("# pbi-agent upgrade\n")


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_guide_has_required_sections(path: CommandPath) -> None:
    guide = _guide_text(path)
    assert guide is not None

    assert guide.splitlines()[0] == f"# {_command_label(path)}"
    assert guide.isascii()
    assert "\x1b" not in guide
    assert not any(line.endswith("\\") for line in guide.splitlines())

    if not path:
        expected = ROOT_SECTIONS
    elif path in PARENT_PATHS:
        expected = PARENT_SECTIONS
    else:
        expected = LEAF_SECTIONS
    sections = _sections(guide)
    assert list(sections) == expected
    for name in expected:
        assert sections[name].strip(), f"{_command_label(path)}: empty {name}"


@pytest.mark.parametrize(
    "path", PARENT_PATHS, ids=[_command_label(path) for path in PARENT_PATHS]
)
def test_parent_guide_lists_children(path: CommandPath) -> None:
    guide = _guide_text(path)
    assert guide is not None
    subcommands = _sections(guide)["Subcommands"]

    for child in _children(PARSERS_BY_PATH[path]):
        child_label = _command_label((*path, child))
        assert f"`{child_label}`" in subcommands
        assert f"`{child_label} --doc`" in subcommands
    assert "--doc" in subcommands


def test_root_guide_indexes_every_command() -> None:
    guide = _guide_text(())
    assert guide is not None
    commands = _sections(guide)["Commands"]

    for path in EXPECTED_PATHS[1:]:
        assert f"`{_command_label(path)}`" in commands
    assert "`pbi-agent update`" in commands
    assert "--doc" in _sections(guide)["Getting more detail"]


def test_upgrade_guide_mentions_update_alias() -> None:
    guide = _guide_text(("upgrade",))
    assert guide is not None
    assert "pbi-agent update" in guide


def _documented_tokens(action: argparse.Action) -> str:
    if action.option_strings:
        return max(action.option_strings, key=len)
    return str(action.metavar or action.dest)


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_guide_documents_every_option(path: CommandPath) -> None:
    guide = _guide_text(path)
    assert guide is not None
    section = "Global options" if not path else "Options and arguments"
    tokens = _backtick_tokens(_sections(guide)[section])

    missing: list[str] = []
    for action in PARSERS_BY_PATH[path]._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if isinstance(
            action, argparse._HelpAction | DocAction | argparse._SubParsersAction
        ):
            continue
        token = _documented_tokens(action)
        if token not in tokens:
            missing.append(token)
    assert missing == []


PATHS_BY_PARSER_ID = {id(parser): path for path, parser in WALK}
FLAG_TOKEN = re.compile(r"^--?[A-Za-z][A-Za-z0-9-]*$")
SNIPPET_SEPARATORS = re.compile(r"[\s,=/|\[\]{}()]+")
FENCED_BLOCK = re.compile(r"^```[A-Za-z]*\n(.*?)^```", flags=re.S | re.M)
# Flags a guide may name in Usage/Options although no pbi-agent parser on its
# path defines them. Keep this to flags of other programs.
FOREIGN_FLAGS: dict[CommandPath, set[str]] = {
    # `--local-source` runs `pip install -e` inside the container.
    ("sandbox",): {"-e"},
}


def _flags_on_path(path: CommandPath) -> set[str]:
    """Option strings of the parser at ``path``, its ancestors and the root."""
    flags: set[str] = set()
    for depth in range(len(path) + 1):
        for action in PARSERS_BY_PATH[path[:depth]]._actions:
            flags.update(action.option_strings)
    return flags


def _referenced_path(words: list[str], default: CommandPath) -> CommandPath:
    """Resolve the command a snippet names (``pbi-agent web --port`` -> web)."""
    if not words or words[0] != "pbi-agent":
        return default
    current = PARSER
    for word in words[1:]:
        action = _subparsers_action(current)
        if action is not None and word in action.choices:
            current = action.choices[word]
    return PATHS_BY_PARSER_ID[id(current)]


def _flag_references(guide: str, path: CommandPath) -> list[tuple[CommandPath, str]]:
    """``(command path, flag)`` for each flag in the Usage and Options sections."""
    sections = _sections(guide)
    options = "Global options" if not path else "Options and arguments"
    snippets: list[str] = []
    for name in ("Usage", options):
        text = sections[name]
        for block in FENCED_BLOCK.findall(text):
            snippets.extend(block.splitlines())
        snippets.extend(re.findall(r"`([^`\n]+)`", FENCED_BLOCK.sub("", text)))

    references: list[tuple[CommandPath, str]] = []
    for snippet in snippets:
        words = [word for word in SNIPPET_SEPARATORS.split(snippet) if word]
        target = _referenced_path(words, path)
        references.extend((target, word) for word in words if FLAG_TOKEN.match(word))
    return references


def _stale_flags(guide: str, path: CommandPath) -> list[str]:
    allowed = FOREIGN_FLAGS.get(path, set())
    return [
        f"{_command_label(target)} {flag}"
        for target, flag in _flag_references(guide, path)
        if flag not in _flags_on_path(target) and flag not in allowed
    ]


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_guide_names_only_existing_options(path: CommandPath) -> None:
    guide = _guide_text(path)
    assert guide is not None

    assert _stale_flags(guide, path) == []


def test_stale_option_check_flags_removed_option() -> None:
    guide = _guide_text(("init",))
    assert guide is not None
    stale = guide.replace("[--force]", "[--force] [--zz-removed]", 1)
    stale += "\n- `--zz-gone`: removed.\n- See `pbi-agent web --zz-port`.\n"
    stale = stale.replace("## Examples", "- `--zz-option`: removed.\n\n## Examples")

    assert _stale_flags(stale, ("init",)) == [
        "pbi-agent init --zz-removed",
        "pbi-agent init --zz-option",
    ]


def _usage_units(usage: str) -> list[str]:
    """Split a usage line into top-level words and ``[...]`` groups."""
    units: list[str] = []
    current = ""
    depth = 0
    for char in usage:
        if char == " " and depth == 0:
            if current:
                units.append(current)
            current = ""
            continue
        depth += {"[": 1, "]": -1}.get(char, 0)
        current += char
    if current:
        units.append(current)
    return units


def _usage_skeleton(usage: str, prog: str) -> list[str]:
    """Options and positionals of a usage line, in order, without metavars.

    Normalizes the deliberate guide differences: the ``[GLOBAL OPTIONS]`` and
    ``[SANDBOX OPTIONS]`` prefixes, guide-chosen metavars, subcommand
    placeholders (``<action> ...``), and argparse's ``[-h]`` and ``[--doc]``.
    """
    usage = " ".join(usage.split()).removeprefix("usage: ")
    for marker in ("[GLOBAL OPTIONS]", "[SANDBOX OPTIONS]"):
        usage = usage.replace(f" {marker}", "")
    assert usage == prog or usage.startswith(f"{prog} "), usage

    items: list[str] = []
    after_required_option = False
    for unit in _usage_units(usage[len(prog) :]):
        optional = unit.startswith("[")
        inner = unit[1:-1] if optional else unit
        if inner.startswith("<") or "..." in inner or inner.endswith("OPTIONS"):
            after_required_option = False
            continue
        if not optional and after_required_option and not inner.startswith("-"):
            after_required_option = False
            continue
        for alternative in inner.split(" | "):
            name = alternative.split()[0]
            items.append(f"[{name}]" if optional else name)
        after_required_option = not optional and inner.startswith("-")
    return [item for item in items if item not in {"[-h]", "[--doc]"}]


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_guide_usage_matches_argparse(path: CommandPath, wide_terminal) -> None:
    guide = _guide_text(path)
    assert guide is not None
    blocks = FENCED_BLOCK.findall(_sections(guide)["Usage"])
    assert blocks, f"{_command_label(path)} has no usage block"
    # The first line is the canonical form. Later lines are deliberate extras
    # (the `update` alias, the root `--doc` form, a subcommand summary); their
    # flags are covered by test_guide_names_only_existing_options.
    documented = blocks[0].splitlines()[0]
    parser = PARSERS_BY_PATH[path]
    generated = parser.format_usage()

    if not path:
        assert documented == " ".join(generated.split()).removeprefix("usage: ")
    assert _usage_skeleton(documented, parser.prog) == _usage_skeleton(
        generated, parser.prog
    )


def _example_argvs(guide: str) -> list[list[str]]:
    argvs: list[list[str]] = []
    for block in _code_blocks(guide, "bash"):
        for line in block.splitlines():
            assert not line.rstrip().endswith("\\"), line
            tokens = shlex.split(line, comments=True)
            while tokens and ENV_ASSIGNMENT.match(tokens[0]):
                tokens.pop(0)
            if not tokens or tokens[0] != "pbi-agent":
                continue
            argv: list[str] = []
            for token in tokens[1:]:
                if token in SHELL_OPERATORS or token.startswith((">", "2>")):
                    break
                argv.append(token)
            argvs.append(argv)
    return argvs


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_guide_examples_parse(path: CommandPath) -> None:
    guide = _guide_text(path)
    assert guide is not None
    argvs = _example_argvs(guide)
    assert argvs, f"{_command_label(path)} has no runnable examples"

    for argv in argvs:
        parser = cli_parser.build_parser()
        stderr = io.StringIO()
        try:
            with patch("sys.stdout", io.StringIO()), patch("sys.stderr", stderr):
                parser.parse_args(cli_parser._argv_with_default_command(parser, argv))
        except SystemExit as exc:
            assert exc.code == 0, f"{shlex.join(argv)}: {stderr.getvalue()}"


_SIDE_EFFECT_ARGVS = [
    ["run", "--doc"],
    ["web", "--doc"],
    ["config", "providers", "create", "--doc"],
]


def _snapshot(*roots: Path) -> set[Path]:
    return {entry for root in roots for entry in root.rglob("*")}


@pytest.mark.parametrize("argv", _SIDE_EFFECT_ARGVS, ids=shlex.join)
def test_doc_has_no_side_effects(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    workdir = tmp_path / "work"
    home.mkdir()
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(workdir)
    before = _snapshot(tmp_path)

    forbidden = AssertionError("--doc must exit before this runs")
    with (
        patch.object(cli_entrypoint, "run_startup_maintenance", side_effect=forbidden),
        patch.object(cli_entrypoint, "resolve_runtime", side_effect=forbidden),
        patch.object(cli_entrypoint, "resolve_web_runtime", side_effect=forbidden),
        patch.object(cli_entrypoint, "configure_logging", side_effect=forbidden),
        patch.object(cli_entrypoint, "_handle_run_command", side_effect=forbidden),
        patch.object(cli_entrypoint, "_handle_web_command", side_effect=forbidden),
        patch.object(cli_entrypoint, "_handle_config_command", side_effect=forbidden),
        patch("pbi_agent.config.load_dotenv", side_effect=forbidden),
        patch("urllib.request.urlopen", side_effect=forbidden),
        patch("socket.create_connection", side_effect=forbidden),
    ):
        code, stdout, stderr = _run_main(argv)

    assert code == 0
    assert stdout.startswith("# pbi-agent ")
    assert stderr == ""
    assert _snapshot(tmp_path) == before


def _isolated_env(home: Path) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("PBI_AGENT_") and not name.endswith("_API_KEY")
    }
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def _run_subprocess(
    argv: list[str], base: Path
) -> tuple[subprocess.CompletedProcess[str], set[str], Path]:
    home = base / "home"
    workdir = base / "work"
    home.mkdir(parents=True)
    workdir.mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, "-m", "pbi_agent", *argv],
        cwd=workdir,
        env=_isolated_env(home),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    created = {
        entry.relative_to(home).as_posix()
        for entry in home.rglob("*")
        if entry.is_file()
    }
    return result, created, workdir


@pytest.mark.parametrize("argv", _SIDE_EFFECT_ARGVS, ids=shlex.join)
def test_doc_subprocess_matches_help_side_effects(
    argv: list[str], tmp_path: Path
) -> None:
    doc_result, doc_created, doc_workdir = _run_subprocess(argv, tmp_path / "doc")
    help_argv = [*argv[:-1], "--help"]
    help_result, help_created, _ = _run_subprocess(help_argv, tmp_path / "help")

    assert doc_result.returncode == 0, doc_result.stderr
    assert doc_result.stdout.startswith("# pbi-agent ")
    assert doc_result.stderr == ""
    assert help_result.returncode == 0, help_result.stderr
    assert ".pbi-agent/config.json" not in doc_created
    assert list(doc_workdir.iterdir()) == []
    assert doc_created == help_created


@pytest.mark.parametrize("path", EXPECTED_PATHS, ids=PATH_IDS)
def test_help_mentions_doc(path: CommandPath, wide_terminal) -> None:
    target = cli_parser.build_parser()
    for part in path:
        action = _subparsers_action(target)
        assert action is not None
        target = action.choices[part]
    rendered = target.format_help()
    collapsed = " ".join(rendered.split())

    assert "--doc" in rendered
    if path:
        assert "[--doc]" in rendered
        assert DOC_HELP in collapsed
    else:
        assert ROOT_DOC_HELP in collapsed
        assert "pbi-agent --doc" in collapsed


def test_argv_with_default_command_keeps_root_doc(no_maintenance) -> None:
    parser = cli_parser.build_parser()

    assert cli_parser._argv_with_default_command(parser, ["--doc"]) == ["--doc"]
    assert cli_parser._argv_with_default_command(parser, ["--verbose", "--doc"]) == [
        "--verbose",
        "--doc",
    ]

    code, stdout, _ = _run_main(["--doc"])
    assert code == 0
    assert stdout.startswith("# pbi-agent\n")
