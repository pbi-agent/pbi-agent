"""Bounded head+tail text buffer for live process output.

Keeps the first ``head_max`` and the last ``tail_max`` characters of a stream,
so long builds keep both the first error and the final summary. A running
character counter lets readers fetch only output they have not seen yet.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

HEAD_MAX_CHARS = 128_000
TAIL_MAX_CHARS = 128_000


@dataclass(slots=True, frozen=True)
class StreamRead:
    text: str
    cursor: int
    skipped: int = 0


class StreamBuffer:
    def __init__(
        self,
        *,
        head_max: int = HEAD_MAX_CHARS,
        tail_max: int = TAIL_MAX_CHARS,
    ) -> None:
        self._lock = threading.Lock()
        self._head_max = head_max
        self._tail_max = tail_max
        self._head: list[str] = []
        self._head_size = 0
        self._tail: deque[str] = deque()
        self._tail_size = 0
        self._total = 0
        self._dropped = False

    @property
    def dropped(self) -> bool:
        """Whether characters between the head and the tail were dropped."""
        with self._lock:
            return self._dropped

    @property
    def total(self) -> int:
        """Number of characters written so far."""
        with self._lock:
            return self._total

    def append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._total += len(text)
            if self._head_size < self._head_max:
                take = text[: self._head_max - self._head_size]
                self._head.append(take)
                self._head_size += len(take)
                text = text[len(take) :]
            if not text:
                return
            self._tail.append(text)
            self._tail_size += len(text)
            while self._tail_size > self._tail_max:
                excess = self._tail_size - self._tail_max
                first = self._tail[0]
                if len(first) <= excess:
                    self._tail.popleft()
                    self._tail_size -= len(first)
                else:
                    self._tail[0] = first[excess:]
                    self._tail_size -= excess
                self._dropped = True

    def text(self) -> str:
        """Return head + tail, with a marker where middle output was dropped."""
        with self._lock:
            head = "".join(self._head)
            tail = "".join(self._tail)
            if not self._dropped:
                return head + tail
            omitted = self._total - self._head_size - self._tail_size
            return f"{head}\n... {omitted} chars dropped ...\n{tail}"

    def read_since(self, cursor: int) -> StreamRead:
        """Return output written after ``cursor`` (a previous ``StreamRead.cursor``).

        ``skipped`` counts unseen characters that were dropped from the middle.
        """
        with self._lock:
            total = self._total
            cursor = max(0, min(cursor, total))
            head = "".join(self._head)
            tail = "".join(self._tail)
            tail_start = total - self._tail_size
            parts: list[str] = []
            skipped = 0
            if cursor < self._head_size:
                parts.append(head[cursor:])
                position = self._head_size
            else:
                position = cursor
            if position < tail_start:
                skipped = tail_start - position
                position = tail_start
            parts.append(tail[position - tail_start :])
            return StreamRead(text="".join(parts), cursor=total, skipped=skipped)
