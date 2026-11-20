"""Built-in long-form Markdown guides printed by ``--doc``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Sequence
from importlib.resources import files
from typing import Any

GUIDES_DIRNAME = "guides"
ROOT_GUIDE_FILENAME = "pbi-agent.md"
DOC_HELP = "Print the long-form Markdown guide for this command and exit."
ROOT_DOC_HELP = (
    "Print the long-form Markdown guide to pbi-agent and all commands, then exit."
)


def iter_parser_paths(
    parser: argparse.ArgumentParser,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    """Yield ``(path, parser)`` depth-first; aliases map to their target once."""
    seen: set[int] = set()
    yield from _iter_parser_paths(parser, path, seen)


def _iter_parser_paths(
    parser: argparse.ArgumentParser,
    path: tuple[str, ...],
    seen: set[int],
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    seen.add(id(parser))
    yield path, parser
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        choices: dict[str, argparse.ArgumentParser] = action.choices  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        for name, subparser in choices.items():
            if id(subparser) in seen:
                continue
            yield from _iter_parser_paths(subparser, (*path, name), seen)


def guide_filename(path: Sequence[str]) -> str:
    if not path:
        return ROOT_GUIDE_FILENAME
    return ".".join(path) + ".md"


def load_guide(path: Sequence[str]) -> str | None:
    resource = files("pbi_agent.cli").joinpath(GUIDES_DIRNAME, guide_filename(path))
    if not resource.is_file():
        return None
    return resource.read_text(encoding="utf-8")


class DocAction(argparse.Action):
    """Print the packaged Markdown guide for a parser path and exit."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: Any = argparse.SUPPRESS,
        help: str | None = None,
        *,
        guide_path: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )
        self.guide_path = guide_path

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        del namespace, values, option_string
        guide = load_guide(self.guide_path)
        if guide is None:
            parser.exit(1, f"pbi-agent: no --doc guide found for `{parser.prog}`.\n")
        stream = sys.stdout
        stream.write(guide.rstrip("\n") + "\n")
        stream.flush()
        parser.exit(0)


def attach_doc_options(root: argparse.ArgumentParser) -> None:
    """Add ``--doc`` to the root parser and every subparser at any depth."""
    for path, parser in list(iter_parser_paths(root)):
        parser.add_argument(
            "--doc",
            action=DocAction,
            guide_path=path,
            help=DOC_HELP if path else ROOT_DOC_HELP,
        )
