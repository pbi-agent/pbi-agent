from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict | str | None


@dataclass(slots=True)
class ApplyPatchCall:
    call_id: str
    operation: dict


@dataclass(slots=True)
class ShellCall:
    call_id: str
    action: dict


@dataclass(slots=True)
class CompletedResponse:
    response_id: str | None
    text: str
    function_calls: list[ToolCall] = field(default_factory=list)
    apply_patch_calls: list[ApplyPatchCall] = field(default_factory=list)
    shell_calls: list[ShellCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.function_calls or self.apply_patch_calls or self.shell_calls)


@dataclass(slots=True)
class AgentOutcome:
    response_id: str | None
    text: str
    tool_errors: bool = False
