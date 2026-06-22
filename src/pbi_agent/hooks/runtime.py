from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi_agent.config import Settings
from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.matchers import hook_matches
from pbi_agent.hooks.output_parser import parse_hook_output
from pbi_agent.hooks.schemas import (
    HookDefinition,
    HookDiscovery,
    HookEventName,
    HookOutputEntry,
    HookRunStatus,
    HookRunSummary,
    ParsedHookOutput,
)
from pbi_agent.observability import RunTracer

_MAX_CAPTURE_CHARS = 12000


@dataclass(slots=True)
class HookRuntimeResult:
    runs: list[HookRunSummary] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None
    additional_context: list[str] = field(default_factory=list)
    updated_input: dict[str, Any] | None = None
    replacement: str | None = None
    continuation_prompt: str | None = None

    @property
    def context_text(self) -> str | None:
        items = [item.strip() for item in self.additional_context if item.strip()]
        return "\n\n".join(items) if items else None


class HookRuntime:
    def __init__(
        self,
        *,
        workspace: Path,
        settings: Settings,
        session_id: str | None = None,
        turn_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        workspace_directory_key: str | None = None,
        agent_name: str = "main",
        agent_type: str = "session_turn",
        discovery: HookDiscovery | None = None,
        tracer: RunTracer | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.settings = settings
        self.session_id = session_id
        self.turn_id = turn_id
        self.model = model
        self.provider = provider or settings.provider
        self.workspace_directory_key = workspace_directory_key
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.discovery = discovery or discover_hooks(self.workspace, settings)
        self.tracer = tracer
        self.stop_hook_active = False

    def with_turn(
        self,
        *,
        turn_id: str | None = None,
        tracer: RunTracer | None = None,
    ) -> "HookRuntime":
        return HookRuntime(
            workspace=self.workspace,
            settings=self.settings,
            session_id=self.session_id,
            turn_id=turn_id,
            model=self.model,
            provider=self.provider,
            workspace_directory_key=self.workspace_directory_key,
            agent_name=self.agent_name,
            agent_type=self.agent_type,
            discovery=self.discovery,
            tracer=tracer or self.tracer,
        )

    def run(
        self,
        event: HookEventName,
        *,
        matcher_value: str | None = None,
        payload: dict[str, Any] | None = None,
        tracer: RunTracer | None = None,
    ) -> HookRuntimeResult:
        event_payload = self._base_payload(event)
        event_payload.update(payload or {})
        runnable_hooks = [
            hook
            for hook in self.discovery.hooks
            if hook.event == event
            and hook.runnable
            and (
                event in {HookEventName.USER_PROMPT_SUBMIT, HookEventName.STOP}
                or hook_matches(hook.matcher, matcher_value)
            )
        ]
        result = HookRuntimeResult()
        if not runnable_hooks:
            return result
        with ThreadPoolExecutor(max_workers=len(runnable_hooks)) as executor:
            futures = {
                executor.submit(
                    self._run_one,
                    hook,
                    event,
                    event_payload,
                    tracer or self.tracer,
                ): hook
                for hook in runnable_hooks
            }
            completed: list[HookRunSummary] = []
            for future in as_completed(futures):
                completed.append(future.result())
        result.runs = sorted(completed, key=lambda item: item.hook.order)
        # Codex uses the last completing rewrite for competing PreToolUse rewrites.
        completion_order = completed
        for summary in completion_order:
            if summary.status not in {HookRunStatus.SUCCESS, HookRunStatus.BLOCKED}:
                continue
            output = summary.output
            if output is None:
                continue
            self._merge_output(event, result, output)
        return result

    def _merge_output(
        self,
        event: HookEventName,
        result: HookRuntimeResult,
        output: ParsedHookOutput,
    ) -> None:
        if output.block_reason and event in {
            HookEventName.PRE_TOOL_USE,
            HookEventName.USER_PROMPT_SUBMIT,
            HookEventName.PRE_COMPACT,
            HookEventName.POST_COMPACT,
        }:
            result.blocked = True
            result.block_reason = output.block_reason
        if output.additional_context:
            result.additional_context.append(output.additional_context)
        if (
            output.system_message
            and output.system_message not in result.additional_context
        ):
            result.additional_context.append(output.system_message)
        if output.updated_input is not None:
            result.updated_input = output.updated_input
        if output.replacement is not None:
            result.replacement = output.replacement
        if output.continuation_prompt:
            result.continuation_prompt = output.continuation_prompt

    def _run_one(
        self,
        hook: HookDefinition,
        event: HookEventName,
        payload: dict[str, Any],
        tracer: RunTracer | None,
    ) -> HookRunSummary:
        started = time.monotonic()
        if tracer is not None:
            tracer.log_event(
                "hook_started",
                metadata=_hook_metadata(hook),
            )
        command = hook.handler.command or ""
        try:
            proc = _run_hook_command(
                command=command,
                payload=json.dumps(payload, separators=(",", ":")),
                cwd=self.workspace,
                timeout=hook.handler.normalized_timeout,
            )
            stdout = _bound_text(proc.stdout)
            stderr = _bound_text(proc.stderr)
            parsed = parse_hook_output(
                event=event,
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode,
            )
            status = HookRunStatus.SUCCESS
            if proc.returncode == 2 and parsed.block_reason:
                status = HookRunStatus.BLOCKED
            elif proc.returncode not in {0, 2}:
                status = HookRunStatus.FAILED
            summary = HookRunSummary(
                hook=hook,
                status=status,
                duration_ms=_duration_ms(started),
                exit_code=proc.returncode,
                entries=_entries(stdout, stderr),
                error_message=stderr.strip() or None
                if status == HookRunStatus.FAILED
                else None,
                output=parsed,
            )
        except subprocess.TimeoutExpired as exc:
            summary = HookRunSummary(
                hook=hook,
                status=HookRunStatus.TIMED_OUT,
                duration_ms=_duration_ms(started),
                entries=_entries(
                    _bound_text(exc.stdout or ""),
                    _bound_text(exc.stderr or ""),
                ),
                error_message=(
                    f"Hook timed out after {hook.handler.normalized_timeout}s"
                ),
            )
        except Exception as exc:
            summary = HookRunSummary(
                hook=hook,
                status=HookRunStatus.FAILED,
                duration_ms=_duration_ms(started),
                error_message=str(exc),
            )
        if tracer is not None:
            tracer.log_event(
                "hook_completed",
                duration_ms=summary.duration_ms,
                success=summary.status
                in {HookRunStatus.SUCCESS, HookRunStatus.BLOCKED},
                error_message=summary.error_message,
                metadata={
                    **_hook_metadata(hook),
                    "status": summary.status.value,
                    "exit_code": summary.exit_code,
                    "entries": [
                        {"stream": entry.stream, "text": entry.text}
                        for entry in summary.entries
                    ],
                },
            )
        return summary

    def _base_payload(self, event: HookEventName) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "cwd": str(self.workspace),
            "hook_event_name": event.value,
            "model": self.model,
            "transcript_path": None,
            "workspace_directory_key": self.workspace_directory_key,
            "provider": self.provider,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
        }


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC") or "cmd.exe", "/C", command]
    return [os.environ.get("SHELL") or "/bin/sh", "-lc", command]


def _run_hook_command(
    *,
    command: str,
    payload: str,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    args = _shell_command(command)
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        **popen_kwargs,
    )
    try:
        stdout, stderr = proc.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_hook_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            exc.cmd,
            exc.timeout,
            output=stdout,
            stderr=stderr,
        ) from exc
    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode or 0,
        stdout=stdout,
        stderr=stderr,
    )


def _kill_hook_process_tree(proc: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            proc.kill()
        return

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        if proc.poll() is None:
            proc.kill()


def _duration_ms(start: float) -> int:
    return max(0, int((time.monotonic() - start) * 1000))


def _bound_text(text: str | bytes | None) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = text or ""
    if len(text) <= _MAX_CAPTURE_CHARS:
        return text
    return text[:_MAX_CAPTURE_CHARS] + "\n...[truncated]"


def _entries(stdout: str, stderr: str) -> tuple[HookOutputEntry, ...]:
    entries: list[HookOutputEntry] = []
    if stdout:
        entries.append(HookOutputEntry(stream="stdout", text=stdout))
    if stderr:
        entries.append(HookOutputEntry(stream="stderr", text=stderr))
    return tuple(entries)


def _hook_metadata(hook: HookDefinition) -> dict[str, Any]:
    return {
        "event": hook.event.value,
        "matcher": hook.matcher,
        "source": hook.source,
        "source_path": str(hook.source_path),
        "order": hook.order,
        "command": hook.handler.command,
        "status_message": hook.handler.status_message,
        "timeout": hook.handler.normalized_timeout,
        "hook_key": hook.key,
        "hook_hash": hook.current_hash,
    }
