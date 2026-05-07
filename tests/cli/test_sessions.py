from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import cli
from pbi_agent.config import (
    DEFAULT_MODEL,
)
from pbi_agent.session_store import SessionStore


class DefaultWebCommandTests(unittest.TestCase):
    _OAUTH_URL = (
        "https://auth.openai.com/oauth/authorize?"
        "response_type=code&client_id=app_EMoamEEZ73f0CkXaXp7hrann"
        "&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback"
        "&scope=openid+profile+email+offline_access"
        "&state=abc123&originator=opencode"
    )

    def _settings(self, *, verbose: bool = False) -> Mock:
        return Mock(
            verbose=verbose,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            sub_agent_model="gpt-5-mini",
            max_tokens=16384,
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=200000,
            service_tier=None,
        )

    def test_main_run_with_session_id_uses_current_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            with SessionStore(db_path=db_path) as store:
                session_id = store.create_session(
                    "/tmp/project", "xai", "grok-4", "saved xai session"
                )

            with (
                patch.dict(
                    os.environ,
                    {
                        "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                        "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                        "PBI_AGENT_PROVIDER": "openai",
                        "PBI_AGENT_MODEL": DEFAULT_MODEL,
                        "OPENAI_API_KEY": "openai-key",
                    },
                    clear=False,
                ),
                patch("pbi_agent.config.load_dotenv"),
                patch("pbi_agent.cli.entrypoint.configure_logging"),
                patch(
                    "pbi_agent.cli.entrypoint._handle_run_command", return_value=0
                ) as mock_run,
            ):
                rc = cli.main(["run", "--prompt", "hello", "--session-id", session_id])

        self.assertEqual(rc, 0)
        args, runtime = mock_run.call_args.args
        self.assertEqual(args.session_id, session_id)
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.model, DEFAULT_MODEL)
        self.assertIsNone(runtime.profile_id)

    def test_main_run_with_session_id_uses_saved_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            saved_project = tmp_path / "saved-project"
            saved_project.mkdir()
            caller_project = tmp_path / "caller-project"
            caller_project.mkdir()
            with SessionStore(db_path=db_path) as store:
                session_id = store.create_session(
                    str(saved_project), "xai", "grok-4", "saved xai session"
                )

            original_cwd = Path.cwd()
            try:
                os.chdir(caller_project)
                with (
                    patch.dict(
                        os.environ,
                        {
                            "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                            "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                            "PBI_AGENT_PROVIDER": "openai",
                            "PBI_AGENT_MODEL": DEFAULT_MODEL,
                            "OPENAI_API_KEY": "openai-key",
                        },
                        clear=False,
                    ),
                    patch("pbi_agent.config.load_dotenv"),
                    patch("pbi_agent.cli.entrypoint.configure_logging"),
                    patch(
                        "pbi_agent.cli.entrypoint._handle_run_command", return_value=0
                    ) as mock_run,
                ):
                    rc = cli.main(
                        ["run", "--prompt", "hello", "--session-id", session_id]
                    )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        args, runtime = mock_run.call_args.args
        self.assertEqual(args.session_id, session_id)
        self.assertEqual(Path(args.project_dir), saved_project)
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.model, DEFAULT_MODEL)

    def test_main_run_with_nonexistent_session_id_exits_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            SessionStore(db_path=db_path).close()

            with (
                patch.dict(
                    os.environ,
                    {
                        "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                        "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                    },
                    clear=False,
                ),
                patch("pbi_agent.config.load_dotenv"),
            ):
                stderr = io.StringIO()
                with patch("sys.stderr", stderr):
                    rc = cli.main(
                        ["run", "--prompt", "hello", "--session-id", "nonexistent-id"]
                    )

        self.assertEqual(rc, 1)
        self.assertIn("not found", stderr.getvalue())
