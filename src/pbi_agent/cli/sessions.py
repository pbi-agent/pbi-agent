from __future__ import annotations

import argparse
import sys

from pbi_agent.session_store import SessionStore
from pbi_agent.workspace_context import current_workspace_context


def _load_session_record(session_id: str):  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint

    try:
        store = SessionStore()
    except Exception as exc:
        print(f"Error: unable to open session store: {exc}", file=sys.stderr)
        return None

    with store:
        session = store.get_session(session_id)

    if session is None:
        print(f"Error: session '{session_id}' not found.", file=sys.stderr)
        return None
    return session


def _handle_sessions_command(args: argparse.Namespace) -> int:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint

    try:
        store = SessionStore()
    except Exception as exc:
        print(f"Error: unable to open session store: {exc}", file=sys.stderr)
        return 1

    with store:
        if args.all_dirs:
            sessions = store.list_all_sessions(limit=args.limit)
        else:
            sessions = store.list_sessions(
                current_workspace_context().directory_key,
                limit=args.limit,
            )

    if not sessions:
        print("No sessions found.")
        return 0

    header = (
        f"{'ID':<34} {'Provider':<12} {'Model':<24} "
        f"{'Title':<24} {'Tokens':>10} {'Cost':>8} {'Updated'}"
    )
    print(header)
    print("-" * len(header))
    for s in sessions:
        title = (s.title[:21] + "...") if len(s.title) > 24 else s.title
        updated = s.updated_at[:19].replace("T", " ")
        tokens = f"{s.total_tokens:,}" if s.total_tokens else "-"
        cost = f"${s.cost_usd:.4f}" if s.cost_usd else "-"
        print(
            f"{s.session_id:<34} {s.provider:<12} {s.model:<24} "
            f"{title:<24} {tokens:>10} {cost:>8} {updated}"
        )
    return 0
