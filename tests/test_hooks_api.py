from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import pbi_agent.hooks.trust as hook_trust
from pbi_agent.config import Settings
from pbi_agent.web.serve import create_app


def test_hooks_api_treats_self_declared_project_managed_as_normal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        hook_trust,
        "DEFAULT_HOOK_STATE_PATH",
        tmp_path / "hooks_state.json",
    )
    hooks_path = tmp_path / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "shell",
                            "hooks": [
                                {"type": "command", "command": "echo normal"},
                                {
                                    "type": "command",
                                    "command": "echo managed",
                                    "managed": True,
                                },
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    app = create_app(Settings(api_key="test-key", provider="openai", model="gpt-5.4"))
    with TestClient(app) as client:
        response = client.get("/api/hooks")
        assert response.status_code == 200
        payload = response.json()
        assert payload["review_required_count"] == 2
        normal = next(
            hook for hook in payload["hooks"] if hook["command"] == "echo normal"
        )
        self_declared = next(
            hook for hook in payload["hooks"] if hook["command"] == "echo managed"
        )
        assert not self_declared["managed"]
        assert self_declared["trust_status"] == "untrusted"
        assert any(
            "ignoring self-declared managed hook" in diagnostic
            for diagnostic in self_declared["diagnostics"]
        )

        trusted = client.post("/api/hooks/trust", json={"key": normal["key"]})
        assert trusted.status_code == 200
        assert trusted.json()["review_required_count"] == 1

        disabled = client.post("/api/hooks/disable", json={"key": self_declared["key"]})
        assert disabled.status_code == 200
        assert (
            next(
                hook
                for hook in disabled.json()["hooks"]
                if hook["key"] == self_declared["key"]
            )["trust_status"]
            == "disabled"
        )
