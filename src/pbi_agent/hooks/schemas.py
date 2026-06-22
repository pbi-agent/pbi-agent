from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal


class HookEventName(StrEnum):
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    STOP = "Stop"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"


class HookTrustStatus(StrEnum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    MODIFIED = "modified"
    DISABLED = "disabled"


class HookRunStatus(StrEnum):
    SKIPPED = "skipped"
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class HookHandlerConfig:
    type: str
    command: str | None = None
    timeout: int | float | None = None
    status_message: str | None = None
    async_: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_timeout(self) -> int:
        if self.timeout is None:
            return 600
        try:
            return max(1, int(self.timeout))
        except (TypeError, ValueError):
            return 600


@dataclass(frozen=True, slots=True)
class HookMatcherGroup:
    event: HookEventName
    matcher: str | None
    handlers: tuple[HookHandlerConfig, ...]
    source: str
    source_path: Path
    order: int


@dataclass(frozen=True, slots=True)
class HookDefinition:
    event: HookEventName
    matcher: str | None
    handler: HookHandlerConfig
    source: str
    source_path: Path
    order: int
    group_order: int
    key: str
    current_hash: str
    trust_status: HookTrustStatus
    diagnostics: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.trust_status != HookTrustStatus.DISABLED

    @property
    def runnable(self) -> bool:
        return self.trust_status == HookTrustStatus.TRUSTED


@dataclass(frozen=True, slots=True)
class HookDiscovery:
    hooks: tuple[HookDefinition, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HookOutputEntry:
    stream: Literal["stdout", "stderr", "system"]
    text: str


@dataclass(frozen=True, slots=True)
class HookRunSummary:
    hook: HookDefinition
    status: HookRunStatus
    duration_ms: int
    exit_code: int | None = None
    entries: tuple[HookOutputEntry, ...] = ()
    error_message: str | None = None
    output: "ParsedHookOutput | None" = None


@dataclass(frozen=True, slots=True)
class ParsedHookOutput:
    continue_: bool = True
    stop_reason: str | None = None
    system_message: str | None = None
    suppress_output: bool = False
    additional_context: str | None = None
    block_reason: str | None = None
    updated_input: dict[str, Any] | None = None
    replacement: str | None = None
    continuation_prompt: str | None = None
