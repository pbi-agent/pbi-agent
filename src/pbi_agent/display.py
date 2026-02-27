"""Centralised CLI display layer.

All user-facing output goes through :class:`Display` so that ``session.py``
never calls ``print()`` directly. Two rendering modes are supported:

* **normal** (default) – concise, colour-coded output.
* **verbose** (``--verbose``) – full technical details (call IDs, timeout,
  working directory, raw JSON args) for debugging.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage

try:  # pragma: no cover - optional runtime dependency
    import textual as _textual
except Exception:  # pragma: no cover - optional runtime dependency
    _textual = None


def _shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


class Display:
    """Single entry-point for every piece of CLI output."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._prompt_session: PromptSession[str] | None = None
        self._prompt_session_unavailable = False
        self._wait_active = False
        self._textual_version = getattr(_textual, "__version__", None)

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

    def _print(self, text: str = "") -> None:
        print(text)

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        self._print("=" * 72)
        self._print(f"PBI AGENT v{__version__}")
        self._print("Transform data into decisions.")
        if self._textual_version:
            self._print(f"UI runtime: Textual {self._textual_version}")
        if model:
            self._print(f"Model: {model}")
        if reasoning_effort:
            self._print(f"Reasoning: {reasoning_effort}")

        if interactive:
            self._print("Interactive mode: type exit or quit to stop.")
            self._print("Alt+Enter for new line, Enter to submit.")
        else:
            self._print(
                single_turn_hint
                or "Single prompt mode: running one request from --prompt."
            )
        self._print("=" * 72)
        self._print()

    def user_prompt(self) -> str:
        self._ensure_prompt_session()
        if self._prompt_session is not None:
            return self._prompt_session.prompt(
                HTML("<ansigreen><b>&gt;</b></ansigreen> ")
            )
        return input("> ")

    def assistant_start(self) -> None:
        self._print()

    def wait_start(self, message: str = "model is processing your request...") -> None:
        if self._wait_active:
            return
        self._wait_active = True
        self._print(f"Thinking: {message}")

    def wait_stop(self) -> None:
        self._wait_active = False

    def stream_delta(self, delta: str) -> None:
        self.wait_stop()
        self._stream_parts.append(delta)
        sys.stdout.write(delta)
        sys.stdout.flush()

    def stream_end(self) -> None:
        self.wait_stop()
        if self._stream_parts:
            self._print()
        self._stream_parts = []

    def stream_abort(self) -> None:
        self.wait_stop()
        self._stream_parts = []

    def render_markdown(self, text: str) -> None:
        self._print()
        self._print(text)

    def session_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        total_secs = int(elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours > 0
            else f"{minutes}:{seconds:02d}"
        )

        self._print()
        self._print(
            "Usage: "
            f"{usage.total_tokens:,} total "
            f"({usage.input_tokens:,} in · {usage.cached_input_tokens:,} cached · {usage.output_tokens:,} out) "
            f"| ${usage.estimated_cost_usd:.3f} | {time_str}"
        )
        self._print()

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        self._print()
        self._print(f"--- Running {n} shell command{'s' if n != 1 else ''} ---")

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
        if timed_out:
            status = "timeout"
        elif exit_code == 0:
            status = "done"
        else:
            status = f"exit {exit_code}"

        if self.verbose:
            self._print(
                f"  $ {cmd_short}  {status} ({call_id}) wd={working_directory} timeout_ms={timeout_ms}"
            )
            return
        self._print(f"  $ {cmd_short}  {status}")

    def patch_start(self, count: int) -> None:
        self._print()
        self._print(f"--- Editing {count} file{'s' if count != 1 else ''} ---")

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
            extra = f" {_shorten(detail, 60)}" if (not success and detail) else ""
        self._print(f"  {operation} {path}  {icon}{extra}")

    def function_start(self, count: int) -> None:
        self._print()
        self._print(f"--- Calling {count} function{'s' if count != 1 else ''} ---")

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
            self._print(f"  {name}()  {icon} ({call_id}) args={args_str}")
            return
        self._print(f"  {name}()  {icon}")

    def tool_group_end(self) -> None:
        self._print("-" * 72)
        self._print()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        self._print(f"  Reconnecting... ({attempt}/{max_retries})")

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        wait_display = f"{wait_seconds:.2f}".rstrip("0").rstrip(".")
        self._print(
            f"  Rate limit reached. Retrying in {wait_display}s ({attempt}/{max_retries})"
        )

    def error(self, message: str) -> None:
        self.stream_abort()
        self._print(f"Error: {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            self._print(message)
