from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import read_file as read_file_tool
from pbi_agent.tools.types import ToolContext


def test_read_file_returns_requested_line_window(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    result = read_file_tool.handle(
        {"path": "notes.txt", "start_line": 2, "max_lines": 2},
        ToolContext(),
    )

    assert result == {
        "path": "notes.txt",
        "start_line": 2,
        "end_line": 3,
        "total_lines": 4,
        "content": "two\nthree\n",
        "has_more_lines": True,
        "windowed": True,
    }


def test_read_file_auto_detects_utf16_bom(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "utf16.txt").write_bytes("hello\nworld\n".encode("utf-16"))

    result = read_file_tool.handle({"path": "utf16.txt"}, ToolContext())

    assert result["path"] == "utf16.txt"
    assert result["content"] == "hello\nworld\n"
    assert result["has_more_lines"] is False
    assert "windowed" not in result


def test_read_file_allows_more_than_default_output_budget(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    long_line = (
        f"prefix-{'x' * (read_file_tool.MAX_READ_FILE_OUTPUT_CHARS // 2)}-suffix"
    )
    (tmp_path / "large.txt").write_text(f"{long_line}\n", encoding="utf-8")

    result = read_file_tool.handle({"path": "large.txt"}, ToolContext())

    assert "content_truncated" not in result
    assert result["content"] == f"{long_line}\n"


def test_read_file_bounds_very_large_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    long_line = (
        f"prefix-{'x' * (read_file_tool.MAX_READ_FILE_OUTPUT_CHARS + 200)}-suffix"
    )
    (tmp_path / "large.txt").write_text(f"{long_line}\n", encoding="utf-8")

    result = read_file_tool.handle({"path": "large.txt"}, ToolContext())

    assert result["content_truncated"] is True
    assert len(result["content"]) <= read_file_tool.MAX_READ_FILE_OUTPUT_CHARS
    assert result["content"].startswith("prefix-")
    assert result["content"].endswith("-suffix\n")
    assert "chars omitted" in result["content"]


def test_read_file_rejects_binary_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")

    result = read_file_tool.handle({"path": "blob.bin"}, ToolContext())

    assert "binary file is not supported" in result["error"]


def test_read_file_reports_empty_files_with_zero_range(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")

    result = read_file_tool.handle({"path": "empty.txt"}, ToolContext())

    assert result == {
        "path": "empty.txt",
        "start_line": 0,
        "end_line": 0,
        "total_lines": 0,
        "content": "",
        "has_more_lines": False,
        "empty": True,
    }
