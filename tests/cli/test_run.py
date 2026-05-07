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
from pbi_agent.cli import run as cli_run
from pbi_agent.config import (
    ModelProfileConfig,
    ProviderConfig,
    create_model_profile_config,
    create_provider_config,
    select_active_model_profile,
)


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

    def test_run_command_uses_active_default_profile(self) -> None:
        create_provider_config(
            ProviderConfig(
                id="openai-main",
                name="OpenAI Main",
                kind="openai",
                api_key="saved-openai-key",
            )
        )
        create_model_profile_config(
            ModelProfileConfig(
                id="analysis",
                name="Analysis",
                provider_id="openai-main",
                model="saved-model",
                reasoning_effort="medium",
            )
        )
        select_active_model_profile("analysis")

        env_overrides = {"PBI_AGENT_API_KEY": "saved-openai-key"}
        env_clear = [
            "PBI_AGENT_PROVIDER",
            "PBI_AGENT_MODEL",
            "PBI_AGENT_SUB_AGENT_MODEL",
            "PBI_AGENT_PROFILE_ID",
            "PBI_AGENT_RESPONSES_URL",
            "PBI_AGENT_GENERIC_API_URL",
            "PBI_AGENT_REASONING_EFFORT",
            "PBI_AGENT_MAX_TOOL_WORKERS",
            "PBI_AGENT_MAX_RETRIES",
            "PBI_AGENT_COMPACT_THRESHOLD",
            "PBI_AGENT_MAX_TOKENS",
            "PBI_AGENT_SERVICE_TIER",
            "PBI_AGENT_WEB_SEARCH",
        ]
        previous_env = {name: os.environ.get(name) for name in env_clear}
        try:
            for name in env_clear:
                os.environ.pop(name, None)
            with (
                patch.dict(os.environ, env_overrides, clear=False),
                patch(
                    "pbi_agent.cli.run._run_single_turn_command", return_value=0
                ) as run_mock,
            ):
                rc = cli.main(["run", "--prompt", "hi"])
        finally:
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.assertEqual(rc, 0)
        runtime = run_mock.call_args.kwargs["settings"]
        self.assertEqual(runtime.provider_id, "openai-main")
        self.assertEqual(runtime.profile_id, "analysis")
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.api_key, "saved-openai-key")
        self.assertEqual(runtime.settings.model, "saved-model")
        self.assertEqual(runtime.settings.reasoning_effort, "medium")

    def test_handle_run_command_uses_single_turn_path(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["run", "--prompt", "Inspect the report"])
        settings = self._settings()
        outcome = Mock(tool_errors=False)

        with (
            patch(
                "pbi_agent.agent.session.run_single_turn", return_value=outcome
            ) as mock_run,
            patch(
                "pbi_agent.display.console_display.ConsoleDisplay"
            ) as mock_display_cls,
        ):
            rc = cli_run._handle_run_command(args, settings)

        self.assertEqual(rc, 0)
        mock_display_cls.assert_called_once_with(verbose=False)
        prompt, runtime, display = mock_run.call_args.args
        self.assertEqual(prompt, "Inspect the report")
        self.assertIs(display, mock_display_cls.return_value)
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(runtime.provider_id, "")
        self.assertEqual(runtime.profile_id, "")
        self.assertEqual(
            mock_run.call_args.kwargs,
            {
                "single_turn_hint": None,
                "image_paths": [],
                "resume_session_id": None,
            },
        )

    def test_handle_run_command_scopes_to_requested_project_dir(self) -> None:
        parser = cli.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            project_dir = root_dir / "report-a"
            project_dir.mkdir()
            args = parser.parse_args(
                [
                    "run",
                    "--prompt",
                    "Inspect the report",
                    "--project-dir",
                    str(project_dir),
                ]
            )
            settings = self._settings()
            seen_cwds: list[Path] = []

            def fake_run_single_turn(
                prompt: str,
                runtime_settings,
                display,
                *,
                single_turn_hint: str | None = None,
                image_paths: list[str] | None = None,
                resume_session_id: str | None = None,
            ) -> object:
                del (
                    prompt,
                    runtime_settings,
                    display,
                    single_turn_hint,
                    image_paths,
                    resume_session_id,
                )
                seen_cwds.append(Path.cwd())
                return Mock(tool_errors=False)

            try:
                os.chdir(root_dir)
                with (
                    patch(
                        "pbi_agent.agent.session.run_single_turn",
                        side_effect=fake_run_single_turn,
                    ) as mock_run,
                    patch(
                        "pbi_agent.display.console_display.ConsoleDisplay"
                    ) as mock_display_cls,
                ):
                    rc = cli_run._handle_run_command(args, settings)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        self.assertEqual(seen_cwds, [project_dir])
        self.assertEqual(Path.cwd(), original_cwd)
        mock_display_cls.assert_called_once_with(verbose=False)
        mock_run.assert_called_once()

    def test_handle_run_command_rejects_missing_project_dir(self) -> None:
        parser = cli.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            args = parser.parse_args(
                [
                    "run",
                    "--prompt",
                    "Inspect the report",
                    "--project-dir",
                    "missing-project",
                ]
            )
            settings = self._settings()
            stderr = io.StringIO()

            try:
                os.chdir(root_dir)
                with patch("sys.stderr", stderr):
                    rc = cli_run._handle_run_command(args, settings)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 1)
        self.assertIn("Project directory does not exist", stderr.getvalue())
