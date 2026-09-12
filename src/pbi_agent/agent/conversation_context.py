from __future__ import annotations

from collections.abc import Sequence

from pbi_agent.session_store import MessageRecord


def model_context_messages(messages: Sequence[MessageRecord]) -> list[MessageRecord]:
    """Exclude explicitly marked local-shell records from model context.

    Each command/output record is marked when persisted, independently of its
    content or neighboring records. Ordinary bang-prefixed prompts and compaction
    markers after unfinished commands must remain in model context.
    """
    return [message for message in messages if not message.is_local_command]
