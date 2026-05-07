from __future__ import annotations

from pbi_agent import cli


def test_facade_exports_main_and_parser() -> None:
    assert callable(cli.main)
    assert callable(cli.build_parser)
    assert cli.build_parser().prog == "pbi-agent"
