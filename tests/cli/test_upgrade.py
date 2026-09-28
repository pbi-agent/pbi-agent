from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

from pbi_agent import cli
from pbi_agent.cli import upgrade
from pbi_agent.self_update import UpdateCheckError, UpgradePlan

UV_PLAN = UpgradePlan(
    installer="uv",
    command=("/bin/uv", "tool", "upgrade", "pbi-agent"),
    manual_hint="Run: uv tool upgrade pbi-agent",
)
SOURCE_PLAN = UpgradePlan(
    installer="source",
    command=None,
    manual_hint="Update your source checkout and reinstall it.",
    problem="pbi-agent is installed from source (file:///src), not from PyPI.",
)


@pytest.fixture
def maintenance(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
    monkeypatch.setattr("pbi_agent.cli.entrypoint.run_startup_maintenance", mock)
    return mock


@pytest.fixture
def upgrade_env(monkeypatch: pytest.MonkeyPatch, maintenance: Mock) -> Mock:
    monkeypatch.setattr(upgrade.sys, "platform", "linux")
    monkeypatch.setattr(upgrade, "__version__", "1.0.0")
    monkeypatch.setattr(upgrade, "latest_pypi_version", lambda: "1.2.0")
    monkeypatch.setattr(upgrade, "detect_upgrade_plan", lambda: UV_PLAN)
    monkeypatch.setattr(upgrade, "installed_version", lambda: "1.2.0")
    run = Mock(return_value=subprocess.CompletedProcess(UV_PLAN.command, 0))
    monkeypatch.setattr(upgrade.subprocess, "run", run)
    return run


def _use_plan(monkeypatch: pytest.MonkeyPatch, plan: UpgradePlan) -> None:
    monkeypatch.setattr(upgrade, "detect_upgrade_plan", lambda: plan)


@pytest.mark.parametrize("command", ["upgrade", "update"])
def test_upgrade_runs_detected_installer(
    command: str, upgrade_env: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([command]) == 0

    upgrade_env.assert_called_once_with(UV_PLAN.command, check=False)
    out = capsys.readouterr().out
    assert "pbi-agent 1.0.0 -> 1.2.0" in out
    assert "pbi-agent upgraded to 1.2.0." in out


def test_upgrade_fails_when_installer_leaves_version_unchanged(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(upgrade, "installed_version", lambda: "1.0.0")

    assert cli.main(["upgrade"]) == 1

    err = capsys.readouterr().err
    assert "uv finished, but pbi-agent is still 1.0.0" in err
    assert "version constraint" in err


def test_upgrade_propagates_installer_failure(
    upgrade_env: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    upgrade_env.return_value = subprocess.CompletedProcess(UV_PLAN.command, 3)

    assert cli.main(["upgrade"]) == 3

    err = capsys.readouterr().err
    assert "upgrade failed (exit code 3)" in err
    assert "Run: uv tool upgrade pbi-agent" in err


def test_upgrade_reports_installer_launch_error(
    upgrade_env: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    upgrade_env.side_effect = FileNotFoundError("uv")

    assert cli.main(["upgrade"]) == 1

    assert "failed to run uv" in capsys.readouterr().err


def test_upgrade_check_reports_available_update_with_exit_100(
    upgrade_env: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["upgrade", "--check"]) == 100

    upgrade_env.assert_not_called()
    assert "Run: pbi-agent upgrade" in capsys.readouterr().out


def test_upgrade_check_on_source_install_reports_update(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_plan(monkeypatch, SOURCE_PLAN)

    assert cli.main(["upgrade", "--check"]) == 100

    captured = capsys.readouterr()
    assert "Update your source checkout and reinstall it." in captured.out
    assert captured.err == ""


def test_upgrade_refuses_source_install(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_plan(monkeypatch, SOURCE_PLAN)

    assert cli.main(["upgrade"]) == 1

    upgrade_env.assert_not_called()
    err = capsys.readouterr().err
    assert "installed from source (file:///src)" in err
    assert "Update your source checkout" in err


def test_upgrade_names_missing_installer(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _use_plan(
        monkeypatch,
        UpgradePlan(
            installer="pipx",
            command=None,
            manual_hint="Run: pipx upgrade pbi-agent",
            problem="pbi-agent was installed with pipx, but `pipx` is not on PATH.",
        ),
    )

    assert cli.main(["upgrade"]) == 1

    upgrade_env.assert_not_called()
    err = capsys.readouterr().err
    assert "installed with pipx, but `pipx` is not on PATH" in err
    assert "Run: pipx upgrade pbi-agent" in err
    assert "uv tool" not in err


def test_upgrade_up_to_date(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(upgrade, "latest_pypi_version", lambda: "1.0.0")

    assert cli.main(["upgrade", "--check"]) == 0
    assert cli.main(["upgrade"]) == 0

    upgrade_env.assert_not_called()
    assert "pbi-agent 1.0.0 is up to date" in capsys.readouterr().out


def test_upgrade_reports_pypi_failure_cause(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def offline() -> str:
        raise UpdateCheckError("URLError: <urlopen error proxy refused>")

    monkeypatch.setattr(upgrade, "latest_pypi_version", offline)

    assert cli.main(["upgrade", "--check"]) == 1

    upgrade_env.assert_not_called()
    assert "proxy refused" in capsys.readouterr().err


def test_upgrade_on_windows_defers_installer_until_exit(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(upgrade.sys, "platform", "win32")
    deferred = ("powershell", "-Command", "wait; upgrade")
    wrap = Mock(return_value=deferred)
    popen = Mock()
    monkeypatch.setattr(upgrade, "windows_deferred_command", wrap)
    monkeypatch.setattr(upgrade.subprocess, "Popen", popen)

    assert cli.main(["upgrade"]) == 0

    wrap.assert_called_once_with(UV_PLAN.command)
    popen.assert_called_once_with(deferred)
    upgrade_env.assert_not_called()
    assert "after pbi-agent exits" in capsys.readouterr().out


def test_upgrade_skips_startup_update_check(
    upgrade_env: Mock, maintenance: Mock
) -> None:
    assert cli.main(["upgrade", "--check"]) == 100

    maintenance.assert_called_once_with(render_notice=True, check_updates=False)


@pytest.mark.parametrize(
    ("flag", "handler"),
    [("--agents", "_handle_agents_flag"), ("--mcp", "_handle_mcp_flag")],
)
def test_global_diagnostic_flags_take_precedence_over_upgrade(
    upgrade_env: Mock,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    handler: str,
) -> None:
    handled = Mock(return_value=0)
    monkeypatch.setattr(f"pbi_agent.cli.entrypoint.{handler}", handled)

    assert cli.main([flag, "upgrade"]) == 0

    handled.assert_called_once()
    upgrade_env.assert_not_called()
