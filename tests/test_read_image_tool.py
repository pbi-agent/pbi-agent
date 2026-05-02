from __future__ import annotations

from pbi_agent.tools import read_image as read_image_tool
from pbi_agent.tools.types import ToolContext, ToolOutput


def test_read_image_returns_summary_and_attachment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    png_bytes = b"\x89PNG\r\n\x1a\nPNGDATA"
    (tmp_path / "chart.png").write_bytes(png_bytes)

    result = read_image_tool.handle({"path": "chart.png"}, ToolContext())

    assert isinstance(result, ToolOutput)
    assert result.result == {
        "path": "chart.png",
        "mime_type": "image/png",
        "byte_count": len(png_bytes),
    }
    assert len(result.attachments) == 1
    assert result.attachments[0].path == "chart.png"
    assert result.attachments[0].mime_type == "image/png"
    assert result.attachments[0].byte_count == len(png_bytes)


def test_read_image_allows_absolute_path_outside_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    png_bytes = b"\x89PNG\r\n\x1a\nPNGDATA"
    outside = tmp_path / "outside.png"
    outside.write_bytes(png_bytes)

    result = read_image_tool.handle({"path": str(outside)}, ToolContext())

    assert isinstance(result, ToolOutput)
    assert result.result["path"] == str(outside.resolve())
    assert result.attachments[0].path == str(outside.resolve())


def test_read_image_rejects_unsupported_formats(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "chart.gif").write_bytes(b"GIF89a")

    result = read_image_tool.handle({"path": "chart.gif"}, ToolContext())

    assert result == {
        "error": "unsupported image format: chart.gif (allowed: JPEG, PNG, WEBP)"
    }
