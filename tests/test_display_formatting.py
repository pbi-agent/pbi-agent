from __future__ import annotations

from pbi_agent.display.formatting import (
    route_function_result,
    tool_group_class,
    tool_item_class,
)


def test_read_image_routes_to_dedicated_cli_display() -> None:
    tool_name, text = route_function_result(
        "read_image",
        status="[green]done[/green]",
        arguments={"path": "docs/shot.png"},
        result={
            "ok": True,
            "result": {
                "path": "docs/shot.png",
                "mime_type": "image/png",
                "byte_count": 24,
            },
        },
    )

    assert tool_name == "read_image"
    assert tool_group_class("read_image") == "tool-group-read-image"
    assert tool_item_class("read_image") == "tool-call-read-image"
    assert "docs/shot.png" in text
    assert "image/png" in text
    assert "24 bytes" in text
    assert "read_image()" not in text


def test_read_image_cli_display_shows_error_detail() -> None:
    _, text = route_function_result(
        "read_image",
        status="[red]failed[/red]",
        arguments={"path": "notes.txt"},
        result={"ok": False, "result": {"error": "unsupported image format"}},
    )

    assert "error:" in text
    assert "unsupported image format" in text


def test_web_search_routes_unwrap_wrapped_result_sources() -> None:
    tool_name, text = route_function_result(
        "web_search",
        status="[green]done[/green]",
        arguments={"query": "btc live price"},
        result={
            "ok": True,
            "result": {
                "sources": [
                    {
                        "title": "BTC USD — Bitcoin Price and Chart",
                        "url": "https://www.tradingview.com/symbols/BTCUSD/",
                        "snippet": "Live Bitcoin price information.",
                    },
                ],
            },
        },
    )

    assert tool_name == "web_search"
    assert "1 source" in text
    assert "BTC USD" in text
    assert "https://www.tradingview.com/symbols/BTCUSD/" in text
    assert "no sources" not in text
