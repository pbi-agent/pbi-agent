from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pbi_agent.tools import python_exec as python_exec_tool
from pbi_agent.tools.types import ToolContext


def test_python_exec_runs_code_in_same_environment_and_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_TEST_FLAG", "present")
    (tmp_path / "helper_module.py").write_text(
        "VALUE = 'workspace import works'\n",
        encoding="utf-8",
    )

    result = python_exec_tool.handle(
        {
            "code": (
                "import json\n"
                "import os\n"
                "import sys\n"
                "from pathlib import Path\n"
                "from helper_module import VALUE\n"
                "payload = {\n"
                "    'cwd': str(Path.cwd()),\n"
                "    'env': os.environ['PBI_AGENT_TEST_FLAG'],\n"
                "    'executable': sys.executable,\n"
                "    'value': VALUE,\n"
                "}\n"
                "print(json.dumps(payload, sort_keys=True))\n"
            )
        },
        ToolContext(),
    )

    assert result["ok"] is True
    assert result["stderr"] == ""
    assert result["error_type"] is None
    assert result["timed_out"] is False
    payload = json.loads(result["stdout"])
    assert payload == {
        "cwd": str(tmp_path.resolve()),
        "env": "present",
        "executable": sys.executable,
        "value": "workspace import works",
    }


def test_python_exec_captures_structured_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = python_exec_tool.handle(
        {
            "code": "result = {'status': 'ok', 'value': 42}",
            "capture_result": True,
        },
        ToolContext(),
    )

    assert result == {
        "ok": True,
        "stdout": "",
        "stderr": "",
        "result": {"status": "ok", "value": 42},
        "error_type": None,
        "error_message": None,
        "timed_out": False,
        "execution_time_ms": result["execution_time_ms"],
        "stdout_truncated": False,
        "stderr_truncated": False,
        "result_truncated": False,
    }
    assert result["execution_time_ms"] >= 0


def test_python_exec_reports_python_exceptions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = python_exec_tool.handle(
        {"code": "raise ValueError('bad input')"},
        ToolContext(),
    )

    assert result["ok"] is False
    assert result["error_type"] == "ValueError"
    assert result["error_message"] == "bad input"
    assert "Traceback" in result["stderr"]
    assert "ValueError: bad input" in result["stderr"]
    assert result["timed_out"] is False


def test_python_exec_enforces_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = python_exec_tool.handle(
        {
            "code": "import time\ntime.sleep(5)",
            "timeout_seconds": 1,
        },
        ToolContext(),
    )

    assert result["ok"] is False
    assert result["error_type"] == "TimeoutError"
    assert result["error_message"] == "Execution exceeded timeout of 1 seconds"
    assert result["timed_out"] is True
    assert result["result"] is None


def test_python_exec_bounds_large_stdout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = python_exec_tool.handle(
        {"code": "print('A' * 50000)"},
        ToolContext(),
    )

    assert result["ok"] is True
    assert result["stdout_truncated"] is True
    assert len(result["stdout"]) <= python_exec_tool.MAX_STDOUT_CHARS
    assert "chars omitted" in result["stdout"]


def test_python_exec_reports_non_serializable_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = python_exec_tool.handle(
        {
            "code": "result = {1, 2, 3}",
            "capture_result": True,
        },
        ToolContext(),
    )

    assert result["ok"] is True
    assert result["result"] is None
    assert "Failed to serialize `result` as JSON" in result["stderr"]
    assert result["error_type"] is None


def test_python_exec_uses_requested_working_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "marker.txt").write_text("hello", encoding="utf-8")

    result = python_exec_tool.handle(
        {
            "code": (
                "from pathlib import Path\n"
                "result = {\n"
                "    'cwd': str(Path.cwd()),\n"
                "    'marker': Path('marker.txt').read_text(encoding='utf-8'),\n"
                "}\n"
            ),
            "working_directory": "nested",
            "capture_result": True,
        },
        ToolContext(),
    )

    assert result["ok"] is True
    assert result["result"] == {
        "cwd": str(nested.resolve()),
        "marker": "hello",
    }


def test_python_exec_rejects_invalid_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent

    result = python_exec_tool.handle(
        {"code": "print('hi')", "working_directory": str(outside)},
        ToolContext(),
    )

    assert result["ok"] is False
    assert result["error_type"] == "ValueError"
    assert "outside workspace" in result["error_message"]
