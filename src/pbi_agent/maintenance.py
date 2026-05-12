from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pbi_agent import __version__
from pbi_agent.config import load_internal_config
from pbi_agent.session_store import SessionStore
from pbi_agent.web.uploads import purge_old_unreferenced_uploads

PYPI_URL = "https://pypi.org/pypi/pbi-agent/json"
UPDATE_COMMAND = "uv tool install pbi-agent --upgrade"


@dataclass(slots=True)
class MaintenanceResult:
    ran: bool
    update_notice: str | None = None


def run_startup_maintenance() -> MaintenanceResult:
    today = datetime.now(timezone.utc).date().isoformat()
    success = False
    claimed = False
    try:
        with SessionStore() as store:
            if not store.claim_daily_maintenance(today):
                return MaintenanceResult(ran=False)
            claimed = True
            retention_days = load_internal_config().maintenance.retention_days
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            store.purge_old_data(cutoff.isoformat())
            referenced_upload_ids = store.referenced_upload_ids()
            purge_old_unreferenced_uploads(
                cutoff=cutoff,
                referenced_upload_ids=referenced_upload_ids,
            )
            notice = check_update_notice()
            if notice:
                render_update_notice(notice)
            success = True
            return MaintenanceResult(ran=True, update_notice=notice)
    except Exception as exc:  # noqa: BLE001 - startup maintenance is best-effort
        print(f"Warning: maintenance skipped: {exc}", file=sys.stderr)
        return MaintenanceResult(ran=False)
    finally:
        if claimed:
            try:
                with SessionStore() as store:
                    store.finish_daily_maintenance(success=success)
            except Exception:  # noqa: BLE001 - best effort bookkeeping
                pass


def check_update_notice() -> str | None:
    latest = _latest_pypi_version()
    if latest is None:
        return None
    if _is_newer_version(latest, __version__):
        return (
            f"Update available: pbi-agent {__version__} -> {latest}. "
            f"Run: {UPDATE_COMMAND}"
        )
    return None


def render_update_notice(notice: str, *, console: Console | None = None) -> None:
    active_console = console or Console(stderr=True)
    body = Text(notice.replace(". Run: ", ".\nRun: "))
    active_console.print(
        Panel(
            body,
            title="Update available",
            border_style="yellow",
            expand=False,
        )
    )


def _latest_pypi_version() -> str | None:
    try:
        request = urllib.request.Request(
            PYPI_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": f"pbi-agent/{__version__}",
            },
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - update checks must be silent on failure
        return None
    if not isinstance(payload, dict):
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return version if isinstance(version, str) and version else None


def _is_newer_version(candidate: str, current: str) -> bool:
    try:
        from packaging.version import Version

        return Version(candidate) > Version(current)
    except Exception:  # noqa: BLE001 - fallback for environments without packaging
        return _version_tuple(candidate) > _version_tuple(current)


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))
