"""Centralised CLI display layer built on Textual-friendly primitives.

All user-facing output goes through :class:`Display` so that ``session.py``
never calls ``print()`` directly.
"""

from __future__ import annotations

import json
import sys
import threading
import time

from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from textual.markup import to_content

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage


def _shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


def _plain_markup(text: str) -> str:
    """Convert Textual markup into plain text for terminal fallback output."""
    return to_content(text).plain


class Display:
    """Single entry-point for every piece of CLI output."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._prompt_session: PromptSession[str] | None = None
        self._prompt_session_unavailable = False
        self._wait_thread: threading.Thread | None = None
        self._wait_stop_event: threading.Event | None = None

    def _ensure_prompt_session(self) -> None:
        if self._prompt_session is not None or self._prompt_session_unavailable:
            return

        kb = KeyBindings()
        kb.add("enter")(lambda event: event.current_buffer.validate_and_handle())
        kb.add("escape", "enter")(lambda event: event.current_buffer.insert_text("\n"))

        try:
            self._prompt_session = PromptSession(
                key_bindings=kb,
                multiline=True,
            )
        except Exception:
            self._prompt_session_unavailable = True

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        logo = [
            "          ████",
            "          ████",
            "      ████ ████",
            "      ████ ████",
            "████ ████ ████",
            "████ ████ ████",
        ]
        print(f"PBI AGENT v{__version__}")
        for row in logo:
            print(row)
        print("Transform data into decisions.")

        if interactive:
            print("Interactive mode: type exit or quit to stop.")
            print("Alt+Enter inserts a new line. Enter submits.")
        else:
            if single_turn_hint is not None:
                print(_plain_markup(single_turn_hint))
            else:
                print("Single prompt mode: running one request from --prompt.")

        if model:
            print(f"Model: {model}")
        if reasoning_effort:
            print(f"Reasoning: {reasoning_effort}")
        print()

    def user_prompt(self) -> str:
        self._ensure_prompt_session()
        if self._prompt_session is not None:
            return self._prompt_session.prompt(HTML("<ansigreen><b>&gt;</b></ansigreen> "))
        return input("> ")

    def assistant_start(self) -> None:
        print()

    def _wait_worker(self, message: str, stop_event: threading.Event) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        index = 0
        while not stop_event.is_set():
            frame = frames[index % len(frames)]
            sys.stdout.write(f"\r{frame} Thinking {message}")
            sys.stdout.flush()
            index += 1
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(message) + 20) + "\r")
        sys.stdout.flush()

    def wait_start(self, message: str = "model is processing your request...") -> None:
        if self._wait_thread is not None:
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._wait_worker,
            args=(message, stop_event),
            daemon=True,
        )
        self._wait_stop_event = stop_event
        self._wait_thread = thread
        thread.start()

    def wait_stop(self) -> None:
        if self._wait_thread is None or self._wait_stop_event is None:
            return
        self._wait_stop_event.set()
        self._wait_thread.join(timeout=1)
        self._wait_thread = None
        self._wait_stop_event = None

    def stream_delta(self, delta: str) -> None:
        self.wait_stop()
        self._stream_parts.append(delta)
        sys.stdout.write(delta)
        sys.stdout.flush()

    def stream_end(self) -> None:
        self.wait_stop()
        if self._stream_parts:
            print()
        self._stream_parts = []

    def stream_abort(self) -> None:
        self.wait_stop()
        self._stream_parts = []

    def render_markdown(self, text: str) -> None:
        print()
        print(text)

    def session_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        total_secs = int(elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes}:{seconds:02d}"

        total = f"{usage.total_tokens:,}"
        inp = f"{usage.input_tokens:,}"
        cached = f"{usage.cached_input_tokens:,}"
        out = f"{usage.output_tokens:,}"
        cost = f"${usage.estimated_cost_usd:.3f}"

        print()
        print(f"{total} tokens ({inp} in · {cached} cached · {out} out) | {cost} | {time_str}")
        print()

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        label = f"Running {n} shell command{'s' if n != 1 else ''}"
        print()
        print(f"--- {label} ---")

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
    ) -> None:
        cmd_short = _shorten(command, 72)

        if self.verbose:
            meta = f" ({call_id}) wd={working_directory} timeout_ms={timeout_ms}"
        else:
            meta = ""

        if timed_out:
            status = "timeout"
        elif exit_code == 0:
            status = "done"
        else:
            status = f"exit {exit_code}"

        print(f"  $ {cmd_short}  {status}{meta}")

    def patch_start(self, count: int) -> None:
        label = f"Editing {count} file{'s' if count != 1 else ''}"
        print()
        print(f"--- {label} ---")

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None:
        icon = "done" if success else "failed"

        if self.verbose:
            extra = f" ({call_id})"
            if detail:
                extra += f" {_shorten(detail, 100)}"
        else:
            extra = ""
            if not success and detail:
                extra = f" {_shorten(detail, 60)}"

        print(f"  {operation} {path}  {icon}{extra}")

    def function_start(self, count: int) -> None:
        label = f"Calling {count} function{'s' if count != 1 else ''}"
        print()
        print(f"--- {label} ---")

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None:
        icon = "done" if success else "failed"

        if self.verbose:
            args_str = _shorten(_compact_json(arguments), 120)
            print(f"  {name}()  {icon} ({call_id}) args={args_str}")
        else:
            print(f"  {name}()  {icon}")

    def tool_group_end(self) -> None:
        print("----------------")
        print()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        print(f"  Reconnecting… ({attempt}/{max_retries})")

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        wait_display = f"{wait_seconds:.2f}".rstrip("0").rstrip(".")
        print(
            f"  Rate limit reached. Retrying in {wait_display}s ({attempt}/{max_retries})"
        )

    def error(self, message: str) -> None:
        self.stream_abort()
        print(f"Error: {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            print(message)
