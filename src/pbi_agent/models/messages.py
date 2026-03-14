from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


# Pricing per 1M tokens:
#   (base_input, cache_write_5m, cache_write_1h, cache_hit, output)
_MODEL_PRICING: dict[str, tuple[float, float, float, float, float]] = {
    "gpt-5.3-codex": (1.75, 1.75, 1.75, 0.175, 14.00),
    "gpt-5.4-2026-03-05": (2.5, 2.5, 2.5, 0.25, 15.00),
    "claude-opus-4-6": (5.00, 6.25, 10.00, 0.50, 25.00),
    "claude-sonnet-4-6": (3.00, 3.75, 6.00, 0.30, 15.00),
}
_DEFAULT_PRICING: tuple[float, float, float, float, float] = (
    1.75,
    1.75,
    1.75,
    0.175,
    14.00,
)


def _pricing_for_model(model: str) -> tuple[float, float, float, float, float]:
    """Return per-MTok prices for *model*.

    Returns ``(base_input, cache_write_5m, cache_write_1h, cache_hit, output)``.
    """
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]
    # Fuzzy match: check if any known key is a prefix of the model string.
    for key, prices in _MODEL_PRICING.items():
        if model.startswith(key):
            return prices
    return _DEFAULT_PRICING


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_write_1h_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    tool_use_tokens: int = 0
    provider_total_tokens: int = 0
    sub_agent_input_tokens: int = 0
    sub_agent_cached_input_tokens: int = 0
    sub_agent_cache_write_tokens: int = 0
    sub_agent_cache_write_1h_tokens: int = 0
    sub_agent_output_tokens: int = 0
    sub_agent_reasoning_tokens: int = 0
    sub_agent_tool_use_tokens: int = 0
    sub_agent_provider_total_tokens: int = 0
    model: str = ""
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def non_cached_input_tokens(self) -> int:
        """Base input tokens charged at the standard input rate.

        For Anthropic, ``input_tokens`` is set to the total input
        (base + cache reads + cache writes) so we subtract out all
        cached / cache-creation components.  For OpenAI the cache-write
        fields are always 0, so this collapses to the old behaviour.
        """
        return max(
            self.input_tokens
            - self.cached_input_tokens
            - self.cache_write_tokens
            - self.cache_write_1h_tokens,
            0,
        )

    @property
    def total_tokens(self) -> int:
        if self.provider_total_tokens > 0:
            return self.provider_total_tokens
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        p_in, p_w5, p_w1h, p_hit, p_out = _pricing_for_model(self.model)
        return (
            (self.non_cached_input_tokens / 1_000_000.0) * p_in
            + (self.cache_write_tokens / 1_000_000.0) * p_w5
            + (self.cache_write_1h_tokens / 1_000_000.0) * p_w1h
            + (self.cached_input_tokens / 1_000_000.0) * p_hit
            + (self.output_tokens / 1_000_000.0) * p_out
        )

    def add(self, other: "TokenUsage") -> None:
        self._add_snapshot(other.snapshot(), as_sub_agent=False)

    def add_sub_agent(self, other: "TokenUsage") -> None:
        self._add_snapshot(other.snapshot(), as_sub_agent=True)

    @property
    def sub_agent_total_tokens(self) -> int:
        if self.sub_agent_provider_total_tokens > 0:
            return self.sub_agent_provider_total_tokens
        return self.sub_agent_input_tokens + self.sub_agent_output_tokens

    @property
    def main_agent_total_tokens(self) -> int:
        return max(self.total_tokens - self.sub_agent_total_tokens, 0)

    def _add_snapshot(
        self, other_snapshot: "TokenUsage", *, as_sub_agent: bool
    ) -> None:
        with self._lock:
            self.input_tokens += other_snapshot.input_tokens
            self.cached_input_tokens += other_snapshot.cached_input_tokens
            self.cache_write_tokens += other_snapshot.cache_write_tokens
            self.cache_write_1h_tokens += other_snapshot.cache_write_1h_tokens
            self.output_tokens += other_snapshot.output_tokens
            self.reasoning_tokens += other_snapshot.reasoning_tokens
            self.tool_use_tokens += other_snapshot.tool_use_tokens
            self.provider_total_tokens += other_snapshot.provider_total_tokens
            if as_sub_agent:
                self.sub_agent_input_tokens += other_snapshot.input_tokens
                self.sub_agent_cached_input_tokens += other_snapshot.cached_input_tokens
                self.sub_agent_cache_write_tokens += other_snapshot.cache_write_tokens
                self.sub_agent_cache_write_1h_tokens += (
                    other_snapshot.cache_write_1h_tokens
                )
                self.sub_agent_output_tokens += other_snapshot.output_tokens
                self.sub_agent_reasoning_tokens += other_snapshot.reasoning_tokens
                self.sub_agent_tool_use_tokens += other_snapshot.tool_use_tokens
                self.sub_agent_provider_total_tokens += (
                    other_snapshot.provider_total_tokens
                )
            if not self.model and other_snapshot.model:
                self.model = other_snapshot.model

    def snapshot(self) -> "TokenUsage":
        with self._lock:
            return TokenUsage(
                input_tokens=self.input_tokens,
                cached_input_tokens=self.cached_input_tokens,
                cache_write_tokens=self.cache_write_tokens,
                cache_write_1h_tokens=self.cache_write_1h_tokens,
                output_tokens=self.output_tokens,
                reasoning_tokens=self.reasoning_tokens,
                tool_use_tokens=self.tool_use_tokens,
                provider_total_tokens=self.provider_total_tokens,
                sub_agent_input_tokens=self.sub_agent_input_tokens,
                sub_agent_cached_input_tokens=self.sub_agent_cached_input_tokens,
                sub_agent_cache_write_tokens=self.sub_agent_cache_write_tokens,
                sub_agent_cache_write_1h_tokens=self.sub_agent_cache_write_1h_tokens,
                sub_agent_output_tokens=self.sub_agent_output_tokens,
                sub_agent_reasoning_tokens=self.sub_agent_reasoning_tokens,
                sub_agent_tool_use_tokens=self.sub_agent_tool_use_tokens,
                sub_agent_provider_total_tokens=self.sub_agent_provider_total_tokens,
                model=self.model,
            )


@dataclass(slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict | str | None


@dataclass(slots=True)
class CompletedResponse:
    response_id: str | None
    text: str
    assistant_messages: list[str] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    function_calls: list[ToolCall] = field(default_factory=list)
    # Reasoning summary text extracted from OpenAI ``reasoning`` output items.
    reasoning_summary: str = ""
    # Detailed reasoning text extracted from OpenAI ``reasoning.content`` items.
    reasoning_content: str = ""
    # Provider-specific opaque data (e.g. raw Anthropic content blocks for
    # history replay).  The session layer never inspects this; only the
    # provider that created the response uses it.
    provider_data: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.function_calls)


@dataclass(slots=True)
class AgentOutcome:
    response_id: str | None
    text: str
    tool_errors: bool = False
