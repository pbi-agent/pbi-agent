from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from pbi_agent import self_update
from pbi_agent.self_update import (
    UpdateCheckError,
    detect_upgrade_plan,
    latest_pypi_version,
    source_install_url,
    windows_deferred_command,
)

MANAGED_ENVS = [
    pytest.param(("uv", "tools", "pbi-agent"), "uv", ("tool", "upgrade"), id="uv"),
    pytest.param(("pipx", "venvs", "pbi-agent"), "pipx", ("upgrade",), id="pipx"),
]


@pytest.fixture(autouse=True)
def registry_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "source_install_url", lambda: None)


def _on_path(monkeypatch: pytest.MonkeyPatch, *, present: bool) -> None:
    monkeypatch.setattr(
        self_update.shutil, "which", lambda name: f"/bin/{name}" if present else None
    )


@pytest.mark.parametrize(("parts", "installer", "subcommand"), MANAGED_ENVS)
def test_detect_managed_env_runs_its_installer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parts: tuple[str, ...],
    installer: str,
    subcommand: tuple[str, ...],
) -> None:
    _on_path(monkeypatch, present=True)

    plan = detect_upgrade_plan(prefix=str(tmp_path.joinpath(*parts)), base_prefix="/")

    assert plan.installer == installer
    assert plan.command == (f"/bin/{installer}", *subcommand, "pbi-agent")
    assert plan.hint == "Run: pbi-agent upgrade"


@pytest.mark.parametrize(("parts", "installer", "subcommand"), MANAGED_ENVS)
def test_detected_installer_missing_from_path_names_that_installer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parts: tuple[str, ...],
    installer: str,
    subcommand: tuple[str, ...],
) -> None:
    _on_path(monkeypatch, present=False)

    plan = detect_upgrade_plan(prefix=str(tmp_path.joinpath(*parts)), base_prefix="/")

    assert plan.installer == installer
    assert plan.command is None
    assert plan.hint == f"Run: {installer} {' '.join(subcommand)} pbi-agent"
    assert plan.problem is not None
    assert f"installed with {installer}" in plan.problem
    assert "not on PATH" in plan.problem


def test_detect_virtualenv_uses_pip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(self_update.importlib.util, "find_spec", lambda name: object())

    plan = detect_upgrade_plan(prefix=str(tmp_path / ".venv"), base_prefix="/usr")

    assert plan.installer == "pip"
    assert plan.command is not None
    assert plan.command[1:] == ("-m", "pip", "install", "--upgrade", "pbi-agent")


def test_detect_system_python_is_unknown(tmp_path: Path) -> None:
    plan = detect_upgrade_plan(prefix=str(tmp_path), base_prefix=str(tmp_path))

    assert plan.installer == "unknown"
    assert plan.command is None
    assert plan.hint == "Run: uv tool install pbi-agent --upgrade"


def test_detect_source_install_takes_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _on_path(monkeypatch, present=True)
    monkeypatch.setattr(
        self_update, "source_install_url", lambda: "file:///home/me/pbi-agent"
    )
    prefix = tmp_path / "uv" / "tools" / "pbi-agent"

    plan = detect_upgrade_plan(prefix=str(prefix), base_prefix="/usr")

    assert plan.installer == "source"
    assert plan.command is None
    assert plan.problem is not None
    assert "file:///home/me/pbi-agent" in plan.problem
    assert plan.hint == "Update your source checkout and reinstall it."


@pytest.mark.parametrize(
    ("direct_url", "expected"),
    [
        (None, None),
        ('{"url": "file:///src", "dir_info": {"editable": true}}', "file:///src"),
        ('{"url": "file:///src", "dir_info": {}}', "file:///src"),
        ('{"url": "https://github.com/x/y", "vcs_info": {}}', "https://github.com/x/y"),
        ("{}", "unknown location"),
        ("not json", None),
    ],
)
def test_source_install_url_reads_direct_url(
    monkeypatch: pytest.MonkeyPatch, direct_url: str | None, expected: str | None
) -> None:
    distribution = Mock()
    distribution.read_text.return_value = direct_url
    monkeypatch.setattr(
        self_update.importlib.metadata, "distribution", lambda name: distribution
    )

    # The autouse fixture patches the module attribute; this name is the original.
    assert source_install_url() == expected


def test_source_install_url_missing_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> None:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(self_update.importlib.metadata, "distribution", missing)

    assert source_install_url() is None


def _deferred_script(*, interactive: bool = True) -> str:
    command = windows_deferred_command(
        ("C:\\Users\\O'Neil\\uv.exe", "tool", "upgrade", "pbi-agent"),
        installer="uv",
        interactive=interactive,
        pid=111,
        parent_pid=222,
        python="C:\\tools\\pbi-agent\\Scripts\\python.exe",
        current_version="1.0.0",
    )
    assert command[:5] == (
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    )
    return command[5]


def test_windows_deferred_command_waits_for_process_and_launcher() -> None:
    script = _deferred_script()

    assert script.startswith("Wait-Process -Id 111 ")
    assert "Get-Process -Id 222 " in script
    assert "ProcessName -eq 'pbi-agent'" in script
    assert script.index("Wait-Process") < script.index("& 'C:\\Users")
    assert script.endswith("exit $code")


def test_windows_deferred_command_captures_installer_exit_code() -> None:
    script = _deferred_script()

    installer = "& 'C:\\Users\\O''Neil\\uv.exe' 'tool' 'upgrade' 'pbi-agent'"
    # $LASTEXITCODE is read right after the installer, before anything else runs.
    assert f"try {{ {installer}; $code = $LASTEXITCODE }}" in script
    assert script.index("$code = 1;") < script.index(installer)
    assert "if ($null -eq $code) { $code = 1 }" in script


def test_windows_deferred_command_verifies_installed_version_on_success() -> None:
    script = _deferred_script()

    check = "& 'C:\\tools\\pbi-agent\\Scripts\\python.exe' '-c' 'import importlib"
    assert check in script
    assert script.index("if ($code -eq 0) { $check = 1;") < script.index(check)
    assert "'pbi-agent' '1.0.0'" in script
    assert "uv finished, but pbi-agent is still 1.0.0." in script


def test_windows_deferred_command_has_no_double_quotes() -> None:
    assert '"' not in _deferred_script(interactive=True)
    assert '"' not in _deferred_script(interactive=False)


def test_windows_deferred_command_pauses_only_when_interactive() -> None:
    interactive = _deferred_script(interactive=True)
    unattended = _deferred_script(interactive=False)

    assert "Read-Host 'Press Enter to close'" in interactive
    assert "[Console]::KeyAvailable" in interactive
    assert "Read-Host" not in unattended
    assert "KeyAvailable" not in unattended
    assert "Start-Sleep" not in unattended


def _exited_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="runs Windows PowerShell")
@pytest.mark.parametrize(
    ("installer", "python", "current_version", "exit_code", "output"),
    [
        pytest.param(
            (sys.executable, "-c", "pass"),
            sys.executable,
            "0.0.0",
            0,
            "pbi-agent upgraded to ",
            id="upgraded",
        ),
        pytest.param(
            (sys.executable, "-c", "pass"),
            sys.executable,
            None,
            1,
            "fake finished, but pbi-agent is still ",
            id="pinned",
        ),
        pytest.param(
            (sys.executable, "-c", "raise SystemExit(7)"),
            sys.executable,
            "0.0.0",
            7,
            "pbi-agent upgrade failed (exit code 7).",
            id="installer-fails",
        ),
        pytest.param(
            ("C:\\missing\\installer.exe", "upgrade"),
            sys.executable,
            "0.0.0",
            1,
            "pbi-agent upgrade failed (exit code 1).",
            id="installer-missing",
        ),
        pytest.param(
            (sys.executable, "-c", "pass"),
            "C:\\missing\\python.exe",
            "0.0.0",
            0,
            "installed pbi-agent version could not be read",
            id="version-unreadable",
        ),
    ],
)
def test_windows_deferred_command_runs_in_powershell(
    installer: tuple[str, ...],
    python: str,
    current_version: str | None,
    exit_code: int,
    output: str,
) -> None:
    if current_version is None:
        current_version = importlib.metadata.version("pbi-agent")
    pid = _exited_pid()
    command = windows_deferred_command(
        installer,
        installer="fake",
        interactive=False,
        pid=pid,
        parent_pid=pid,
        python=python,
        current_version=current_version,
    )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )

    assert completed.returncode == exit_code, completed.stdout + completed.stderr
    assert output in completed.stdout


def test_latest_pypi_version_uses_json_request_headers_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    make_http_response: Callable[[dict[str, Any]], object],
) -> None:
    urlopen = Mock(return_value=make_http_response({"info": {"version": "1.2.3"}}))
    monkeypatch.setattr(self_update, "__version__", "1.0.0")
    monkeypatch.setattr(self_update.urllib.request, "urlopen", urlopen)

    assert latest_pypi_version() == "1.2.3"
    assert urlopen.call_args.kwargs == {"timeout": 10}
    assert latest_pypi_version(timeout=2) == "1.2.3"
    assert urlopen.call_args.kwargs == {"timeout": 2}

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://pypi.org/pypi/pbi-agent/json"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("User-agent") == "pbi-agent/1.0.0"


def test_latest_pypi_version_reports_network_error_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        self_update.urllib.request,
        "urlopen",
        Mock(side_effect=OSError("proxy refused")),
    )

    with pytest.raises(UpdateCheckError, match="OSError: proxy refused"):
        latest_pypi_version()


def test_latest_pypi_version_rejects_payload_without_version(
    monkeypatch: pytest.MonkeyPatch,
    make_http_response: Callable[[dict[str, Any]], object],
) -> None:
    monkeypatch.setattr(
        self_update.urllib.request,
        "urlopen",
        Mock(return_value=make_http_response({"info": {}})),
    )

    with pytest.raises(UpdateCheckError, match="did not include a version"):
        latest_pypi_version()
