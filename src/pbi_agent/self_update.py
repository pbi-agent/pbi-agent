"""Check PyPI for pbi-agent releases and plan an in-place upgrade."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pbi_agent import __version__

PACKAGE_NAME = "pbi-agent"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
UV_TOOL_UPGRADE_COMMAND = ("uv", "tool", "upgrade", PACKAGE_NAME)
PIPX_UPGRADE_COMMAND = ("pipx", "upgrade", PACKAGE_NAME)
PIP_UPGRADE_ARGS = ("-m", "pip", "install", "--upgrade", PACKAGE_NAME)
FALLBACK_UPGRADE_COMMAND = ("uv", "tool", "install", PACKAGE_NAME, "--upgrade")
SELF_UPGRADE_COMMAND = "pbi-agent upgrade"
# Deferred Windows upgrade: how long the success window stays open, and the exit
# code the version check uses for "still the old version". The check prints the
# installed version and must not contain quotes (see windows_deferred_command).
_SUCCESS_PAUSE_SECONDS = 5
_VERSION_UNCHANGED_EXIT = 3
_VERSION_CHECK_CODE = (
    "import importlib.metadata as m, sys; v = m.version(sys.argv[1]); print(v); "
    f"sys.exit({_VERSION_UNCHANGED_EXIT} if v == sys.argv[2] else 0)"
)


class UpdateCheckError(RuntimeError):
    """Raised when the latest published version cannot be determined."""


@dataclass(frozen=True, slots=True)
class UpgradePlan:
    """How to upgrade this install; ``problem`` explains a None ``command``."""

    installer: str
    command: tuple[str, ...] | None
    manual_hint: str
    problem: str | None = None

    @property
    def hint(self) -> str:
        if self.command is not None:
            return f"Run: {SELF_UPGRADE_COMMAND}"
        return self.manual_hint


def latest_pypi_version(*, timeout: float = 10) -> str:
    """Return the latest pbi-agent version on PyPI or raise UpdateCheckError."""
    request = urllib.request.Request(
        PYPI_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": f"pbi-agent/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateCheckError(f"{type(exc).__name__}: {exc}") from exc
    info = payload.get("info") if isinstance(payload, dict) else None
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str) or not version:
        raise UpdateCheckError("PyPI response did not include a version.")
    return version


def is_newer_version(candidate: str, current: str) -> bool:
    try:
        from packaging.version import Version

        return Version(candidate) > Version(current)
    except Exception:
        return _version_tuple(candidate) > _version_tuple(current)


def update_available_message(current: str, latest: str) -> str:
    return f"Update available: pbi-agent {current} -> {latest}."


def detect_upgrade_plan(
    *,
    prefix: str | None = None,
    base_prefix: str | None = None,
) -> UpgradePlan:
    source = source_install_url()
    if source is not None:
        return UpgradePlan(
            installer="source",
            command=None,
            manual_hint="Update your source checkout and reinstall it.",
            problem=f"pbi-agent is installed from source ({source}), not from PyPI.",
        )

    prefix_path = Path(prefix or sys.prefix).resolve()
    parts = [part.lower() for part in prefix_path.parts]

    # uv tools live under <uv dir>/tools/<pkg>; pipx under <pipx dir>/venvs/<pkg>.
    if _is_managed_env(parts, owner="uv", container="tools"):
        return _installer_plan(UV_TOOL_UPGRADE_COMMAND)
    if _is_managed_env(parts, owner="pipx", container="venvs"):
        return _installer_plan(PIPX_UPGRADE_COMMAND)

    in_virtualenv = prefix_path != Path(base_prefix or sys.base_prefix).resolve()
    if in_virtualenv and importlib.util.find_spec("pip") is not None:
        return UpgradePlan(
            installer="pip",
            command=(sys.executable, *PIP_UPGRADE_ARGS),
            manual_hint=f"Run: python {' '.join(PIP_UPGRADE_ARGS)}",
        )
    return UpgradePlan(
        installer="unknown",
        command=None,
        manual_hint=f"Run: {' '.join(FALLBACK_UPGRADE_COMMAND)}",
        problem="could not detect how pbi-agent was installed.",
    )


def source_install_url() -> str | None:
    """Return the direct URL for non-index installs (editable, path, VCS, archive).

    PEP 610 ``direct_url.json`` is only written for installs that did not come
    from a package index, so its presence means PyPI upgrades do not apply.
    """
    try:
        raw = importlib.metadata.distribution(PACKAGE_NAME).read_text("direct_url.json")
        payload = json.loads(raw or "null")
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    url = payload.get("url")
    return url if isinstance(url, str) and url else "unknown location"


def installed_version() -> str | None:
    """Read the installed version from disk, bypassing import-time caches."""
    importlib.invalidate_caches()
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


def windows_deferred_command(
    command: tuple[str, ...],
    *,
    installer: str,
    interactive: bool,
    pid: int | None = None,
    parent_pid: int | None = None,
    python: str | None = None,
    current_version: str | None = None,
) -> tuple[str, ...]:
    """Wrap ``command`` so it runs after this process (and its launcher) exit.

    On Windows the running ``pbi-agent.exe`` launcher, ``python.exe``, and loaded
    extension modules are locked, so the installer cannot replace them while we
    are alive. PowerShell waits for both processes, then runs the installer.
    The caller runs it in its own console window: sharing the user's console
    would print installer output after the shell has already redrawn its
    prompt, which looks like a hung command.

    After a successful install, the environment's own ``python`` reports the
    installed version so a pinned install is not reported as upgraded. The
    window only pauses when ``interactive``; otherwise nobody can dismiss it.
    The script avoids double quotes so it does not depend on how
    powershell.exe unescapes ``\\"`` in its command line.
    """
    current_pid = os.getpid() if pid is None else pid
    launcher_pid = os.getppid() if parent_pid is None else parent_pid
    invocation = " ".join(_powershell_quote(part) for part in command)
    version_check = " ".join(
        _powershell_quote(part)
        for part in (
            python or sys.executable,
            "-c",
            _VERSION_CHECK_CODE,
            PACKAGE_NAME,
            current_version or __version__,
        )
    )
    still_old = _powershell_quote(
        f"{installer} finished, but pbi-agent is still "
        f"{current_version or __version__}. A version constraint in the original "
        "install may be pinning it; reinstall without the constraint."
    )
    if interactive:
        success_pause = (
            f"Write-Host 'This window closes in {_SUCCESS_PAUSE_SECONDS} seconds; "
            "press any key to close it now.'; "
            f"$deadline = (Get-Date).AddSeconds({_SUCCESS_PAUSE_SECONDS}); "
            "try { while ((Get-Date) -lt $deadline -and -not [Console]::KeyAvailable) "
            "{ Start-Sleep -Milliseconds 200 } } catch {} "
        )
        failure_pause = "Read-Host 'Press Enter to close' | Out-Null "
    else:
        success_pause = failure_pause = ""
    script = (
        f"Wait-Process -Id {current_pid} -ErrorAction SilentlyContinue; "
        f"$launcher = Get-Process -Id {launcher_pid} -ErrorAction SilentlyContinue; "
        "if ($launcher -and $launcher.ProcessName -eq 'pbi-agent') "
        "{ $launcher.WaitForExit() }; "
        # A command that cannot start leaves $LASTEXITCODE unset; `exit $null`
        # would report success, so default to failure and read it immediately.
        "$code = 1; "
        f"try {{ & {invocation}; $code = $LASTEXITCODE }} catch {{ Write-Host $_ }}; "
        "if ($null -eq $code) { $code = 1 }; "
        "if ($code -eq 0) { "
        "$check = 1; "
        f"try {{ $installed = & {version_check}; $check = $LASTEXITCODE }} catch {{}}; "
        "if ($check -eq 0) { Write-Host ('pbi-agent upgraded to ' + $installed + '.') } "
        f"elseif ($check -eq {_VERSION_UNCHANGED_EXIT}) {{ $code = 1; Write-Host {still_old} }} "
        "else { Write-Host 'Upgrade finished, but the installed pbi-agent version "
        "could not be read.' } "
        "}; "
        "if ($code -eq 0) { "
        f"{success_pause}"
        "} else { "
        "Write-Host ('pbi-agent upgrade failed (exit code ' + $code + ').'); "
        f"{failure_pause}"
        "}; "
        "exit $code"
    )
    return (
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    )


def _installer_plan(template: tuple[str, ...]) -> UpgradePlan:
    installer = template[0]
    executable = shutil.which(installer)
    return UpgradePlan(
        installer=installer,
        command=(executable, *template[1:]) if executable else None,
        manual_hint=f"Run: {' '.join(template)}",
        problem=None
        if executable
        else f"pbi-agent was installed with {installer}, but `{installer}` is not on PATH.",
    )


def _is_managed_env(parts: list[str], *, owner: str, container: str) -> bool:
    return len(parts) >= 3 and parts[-2] == container and owner in parts[:-2]


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
