from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    @property
    def non_cached_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        # Pricing per 1M tokens:
        # input=$1.75, cached_input=$0.175, output=$14.00
        return (
            (self.non_cached_input_tokens / 1_000_000.0) * 1.75
            + (self.cached_input_tokens / 1_000_000.0) * 0.175
            + (self.output_tokens / 1_000_000.0) * 14.00
        )

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens


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
    usage: TokenUsage = field(default_factory=TokenUsage)
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
