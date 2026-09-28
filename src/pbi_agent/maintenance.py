from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pbi_agent import __version__
from pbi_agent.config import load_internal_config
from pbi_agent.self_update import (
    UpdateCheckError,
    detect_upgrade_plan,
    is_newer_version,
    latest_pypi_version,
    update_available_message,
)
from pbi_agent.session_store import SessionStore
from pbi_agent.web.uploads import purge_old_unreferenced_uploads

BACKGROUND_CHECK_TIMEOUT_SECONDS = 2


@dataclass(slots=True)
class MaintenanceResult:
    ran: bool
    update_notice: str | None = None


def run_startup_maintenance(
    *, render_notice: bool = True, check_updates: bool = True
) -> MaintenanceResult:
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
            notice = check_update_notice() if check_updates else None
            if notice and render_notice:
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
    try:
        latest = latest_pypi_version(timeout=BACKGROUND_CHECK_TIMEOUT_SECONDS)
    except UpdateCheckError:
        return None  # background update checks stay silent on failure
    if not is_newer_version(latest, __version__):
        return None
    message = update_available_message(__version__, latest)
    return f"{message}\n{detect_upgrade_plan().hint}"


def render_update_notice(
    notice: str,
    *,
    console: Console | None = None,
    centered: bool = False,
) -> None:
    active_console = console or Console(stderr=True)
    panel = Panel(
        Text(notice),
        title="Update available",
        border_style="yellow",
        expand=False,
    )
    active_console.print(Align.center(panel) if centered else panel)
