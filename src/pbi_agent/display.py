"""Centralised CLI display layer.

All user-facing output goes through :class:`Display` so that ``session.py``
never calls ``print()`` directly.
"""

from __future__ import annotations

import json
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings

from textual import __version__ as textual_version

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


class Display:
    """Single entry-point for every piece of CLI output."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._prompt_session: PromptSession[str] | None = None
        self._prompt_session_unavailable = False
        self._showing_wait = False

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
        mode_hint = (
            "Interactive mode: Type exit or quit to stop. Alt+Enter adds a new line."
            if interactive
            else (
                single_turn_hint
                if single_turn_hint is not None
                else "Single prompt mode: Running one request from --prompt."
            )
        )
        model_bits: list[str] = []
        if model:
            model_bits.append(f"model={model}")
        if reasoning_effort:
            model_bits.append(f"reasoning={reasoning_effort}")
        model_line = f" ({', '.join(model_bits)})" if model_bits else ""

        print()
        print("=" * 72)
        print(f"PBI AGENT v{__version__}{model_line}")
        print(f"UI: Textual {textual_version}")
        print("Transform data into decisions.")
        print(mode_hint)
        print("=" * 72)
        print()

    def user_prompt(self) -> str:
        self._ensure_prompt_session()
        if self._prompt_session is not None:
            return self._prompt_session.prompt(HTML("<ansigreen><b>&gt;</b></ansigreen> "))
        return input("> ")

    def assistant_start(self) -> None:
        print()

    def wait_start(self, message: str = "model is processing your request...") -> None:
        if self._showing_wait:
            return
        self._showing_wait = True
        print(f"[thinking] {message}")

    def wait_stop(self) -> None:
        self._showing_wait = False

    def stream_delta(self, delta: str) -> None:
        self.wait_stop()
        self._stream_parts.append(delta)

    def stream_end(self) -> None:
        self.wait_stop()
        text = "".join(self._stream_parts)
        if text.strip():
            print(text)
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
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"

        print()
        print(
            f"tokens={usage.total_tokens:,} "
            f"(in={usage.input_tokens:,} · cached={usage.cached_input_tokens:,} · out={usage.output_tokens:,}) "
            f"| cost=${usage.estimated_cost_usd:.3f} | elapsed={time_str}"
        )
        print()

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        print()
        print(f"--- Running {n} shell command{'s' if n != 1 else ''} ---")

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
        print()
        print(f"--- Editing {count} file{'s' if count != 1 else ''} ---")

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
            extra = f" ({call_id})" if call_id else ""
            if detail:
                extra += f" {_shorten(detail, 100)}"
        else:
            extra = f" {_shorten(detail, 60)}" if (not success and detail) else ""

        print(f"  {operation} {path}  {icon}{extra}")

    def function_start(self, count: int) -> None:
        print()
        print(f"--- Calling {count} function{'s' if count != 1 else ''} ---")

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
        print("-" * 40)
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
        print(f"  Rate limit reached. Retrying in {wait_display}s ({attempt}/{max_retries})")

    def error(self, message: str) -> None:
        self.stream_abort()
        print(f"Error: {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            print(message)
