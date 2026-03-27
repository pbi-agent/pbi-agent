from __future__ import annotations

import importlib.resources
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ZERO_PRICING: tuple[float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0)


class ModelCatalog:
    """Registry of model pricing and context window sizes.

    Loads a bundled ``model_catalog.json`` and optionally merges user
    overrides from ``~/.pbi-agent/model_catalog.json``.
    """

    def __init__(self) -> None:
        self._models: dict[str, dict] = {}
        self._default_context_window: int = 200_000
        self._load_bundled()
        self._load_user_overrides()

    # ------------------------------------------------------------------
    def _load_bundled(self) -> None:
        ref = importlib.resources.files("pbi_agent.models").joinpath(
            "model_catalog.json"
        )
        data = json.loads(ref.read_text(encoding="utf-8"))
        self._models.update(data.get("models", {}))
        self._default_context_window = data.get("defaults", {}).get(
            "context_window", self._default_context_window
        )

    def _load_user_overrides(self) -> None:
        user_path = Path.home() / ".pbi-agent" / "model_catalog.json"
        if not user_path.is_file():
            return
        try:
            data = json.loads(user_path.read_text(encoding="utf-8"))
            self._models.update(data.get("models", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # ------------------------------------------------------------------
    def _find_entry(self, model: str) -> dict | None:
        if model in self._models:
            return self._models[model]
        for key, entry in self._models.items():
            if model.startswith(key):
                return entry
        return None

    def get_pricing(self, model: str) -> tuple[float, float, float, float, float]:
        """Return per-MTok prices ``(input, cache_write_5m, cache_write_1h,
        cache_hit, output)`` for *model*.

        Returns all zeros for unknown models.
        """
        entry = self._find_entry(model)
        if entry is None:
            return _ZERO_PRICING
        p = entry.get("pricing")
        if p is None:
            return _ZERO_PRICING
        return (
            p.get("input", 0.0),
            p.get("cache_write_5m", 0.0),
            p.get("cache_write_1h", 0.0),
            p.get("cache_hit", 0.0),
            p.get("output", 0.0),
        )

    def get_context_window(self, model: str) -> int:
        """Return the context window size for *model*."""
        entry = self._find_entry(model)
        if entry is not None:
            return entry.get("context_window", self._default_context_window)
        return self._default_context_window


# Lazy singleton — avoids file I/O at import time.
_catalog: ModelCatalog | None = None


def _get_catalog() -> ModelCatalog:
    global _catalog
    if _catalog is None:
        _catalog = ModelCatalog()
    return _catalog


def context_window_for_model(model: str) -> int:
    """Return the context window size for *model*."""
    return _get_catalog().get_context_window(model)


def _pricing_for_model(model: str) -> tuple[float, float, float, float, float]:
    """Return per-MTok prices for *model*.

    Returns ``(base_input, cache_write_5m, cache_write_1h, cache_hit, output)``.
    """
    return _get_catalog().get_pricing(model)


def _service_tier_multiplier(service_tier: str) -> float:
    """Return the pricing multiplier for an OpenAI service tier."""
    if service_tier == "flex":
        return 0.5
    if service_tier == "priority":
        return 2.0
    return 1.0


def _estimated_cost(
    *,
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int,
    cache_write_1h_tokens: int,
    output_tokens: int,
    service_tier: str = "",
) -> float:
    p_in, p_w5, p_w1h, p_hit, p_out = _pricing_for_model(model)
    non_cached_input_tokens = max(
        input_tokens - cached_input_tokens - cache_write_tokens - cache_write_1h_tokens,
        0,
    )
    cost = (
        (non_cached_input_tokens / 1_000_000.0) * p_in
        + (cache_write_tokens / 1_000_000.0) * p_w5
        + (cache_write_1h_tokens / 1_000_000.0) * p_w1h
        + (cached_input_tokens / 1_000_000.0) * p_hit
        + (output_tokens / 1_000_000.0) * p_out
    )
    if service_tier:
        cost *= _service_tier_multiplier(service_tier)
    return cost


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
    sub_agent_cost_usd: float = 0.0
    context_tokens: int = 0
    model: str = ""
    service_tier: str = ""
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
        main_input_tokens = max(self.input_tokens - self.sub_agent_input_tokens, 0)
        main_cached_input_tokens = max(
            self.cached_input_tokens - self.sub_agent_cached_input_tokens,
            0,
        )
        main_cache_write_tokens = max(
            self.cache_write_tokens - self.sub_agent_cache_write_tokens,
            0,
        )
        main_cache_write_1h_tokens = max(
            self.cache_write_1h_tokens - self.sub_agent_cache_write_1h_tokens,
            0,
        )
        main_output_tokens = max(self.output_tokens - self.sub_agent_output_tokens, 0)
        return (
            _estimated_cost(
                model=self.model,
                input_tokens=main_input_tokens,
                cached_input_tokens=main_cached_input_tokens,
                cache_write_tokens=main_cache_write_tokens,
                cache_write_1h_tokens=main_cache_write_1h_tokens,
                output_tokens=main_output_tokens,
                service_tier=self.service_tier,
            )
            + self.sub_agent_cost_usd
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
                self.sub_agent_cost_usd += other_snapshot.estimated_cost_usd
            else:
                self.sub_agent_cost_usd += other_snapshot.sub_agent_cost_usd
            if other_snapshot.context_tokens and not as_sub_agent:
                self.context_tokens = other_snapshot.context_tokens
            if not self.model and other_snapshot.model:
                self.model = other_snapshot.model
            if not self.service_tier and other_snapshot.service_tier:
                self.service_tier = other_snapshot.service_tier

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
                sub_agent_cost_usd=self.sub_agent_cost_usd,
                context_tokens=self.context_tokens,
                model=self.model,
                service_tier=self.service_tier,
            )


@dataclass(slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict | str | None


@dataclass(slots=True)
class ImageAttachment:
    path: str
    mime_type: str
    data_base64: str
    byte_count: int = 0


@dataclass(slots=True)
class UserTurnInput:
    text: str = ""
    images: list[ImageAttachment] = field(default_factory=list)


@dataclass(slots=True)
class WebSearchSource:
    """A single citation/source returned by a provider's native web search."""

    title: str
    url: str
    snippet: str = ""


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
    # Web search citations returned by the provider's native search tool.
    web_search_sources: list[WebSearchSource] = field(default_factory=list)
    # Whether the provider response included a hosted web search call item.
    had_web_search_call: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.function_calls)


@dataclass(slots=True)
class AgentOutcome:
    response_id: str | None
    text: str
    tool_errors: bool = False
    session_id: str | None = None
