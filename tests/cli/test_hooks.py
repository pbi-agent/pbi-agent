from __future__ import annotations

import json
from pathlib import Path

from pbi_agent.cli.entrypoint import main


def test_hooks_command_lists_hooks(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    hooks_path = tmp_path / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["hooks"]) == 0
    output = capsys.readouterr().out
    assert "Stop [untrusted]" in output
    assert "Settings → Hooks" in output
