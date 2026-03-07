from __future__ import annotations

from pathlib import Path

from pbi_agent.tools import init_report as init_report_tool
from pbi_agent.tools.types import ToolContext


def test_init_report_tool_handle_returns_success(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_init_report(dest: Path, *, force: bool) -> Path:
        seen["dest"] = dest
        seen["force"] = force
        return dest

    monkeypatch.setattr(init_report_tool, "init_report", fake_init_report)

    result = init_report_tool.handle(
        {"dest": str(tmp_path / "report"), "force": True},
        ToolContext(),
    )

    assert result == {
        "success": True,
        "path": str((tmp_path / "report").resolve()),
    }
    assert seen == {
        "dest": (tmp_path / "report").resolve(),
        "force": True,
    }


def test_init_report_tool_handle_returns_file_exists_error(monkeypatch) -> None:
    def fake_init_report(dest: Path, *, force: bool) -> Path:
        del dest, force
        raise FileExistsError("already exists")

    monkeypatch.setattr(init_report_tool, "init_report", fake_init_report)

    result = init_report_tool.handle({"dest": ".", "force": False}, ToolContext())

    assert result == {"success": False, "error": "already exists"}
