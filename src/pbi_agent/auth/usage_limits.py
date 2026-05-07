from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from pbi_agent.auth.models import (
    AUTH_MODE_CHATGPT_ACCOUNT,
    AUTH_MODE_COPILOT_ACCOUNT,
    AUTH_SESSION_STATUS_CONNECTED,
)
from pbi_agent.auth.providers.github_copilot import (
    GITHUB_COPILOT_BACKEND_ID,
    GitHubCopilotAuthBackend,
)
from pbi_agent.auth.providers.openai_chatgpt import (
    OPENAI_CHATGPT_BACKEND_ID,
    OPENAI_CHATGPT_RESPONSES_URL,
    OpenAIChatGPTAuthBackend,
)
from pbi_agent.auth.service import get_provider_auth_status
from pbi_agent.auth.store import load_auth_session
from pbi_agent.config import ConfigError, ProviderConfig

CHATGPT_CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
GITHUB_COPILOT_USAGE_URL = "https://api.github.com/copilot_internal/user"
_USAGE_TIMEOUT_SECS = 30.0


@dataclass(slots=True)
class UsageLimitCredits:
    has_credits: bool | None = None
    unlimited: bool | None = None
    balance: str | None = None


@dataclass(slots=True)
class UsageLimitWindow:
    name: str
    used_percent: float | None = None
    remaining_percent: float | None = None
    window_minutes: int | None = None
    resets_at: int | None = None
    reset_at_iso: str | None = None
    used_requests: int | None = None
    total_requests: int | None = None
    remaining_requests: int | None = None


@dataclass(slots=True)
class UsageLimitBucket:
    id: str
    label: str
    unlimited: bool = False
    overage_allowed: bool = False
    overage_count: int = 0
    status: str = "unknown"
    credits: UsageLimitCredits | None = None
    windows: list[UsageLimitWindow] = field(default_factory=list)


@dataclass(slots=True)
class ProviderUsageLimits:
    provider_id: str
    provider_kind: str
    account_label: str | None
    plan_type: str | None
    fetched_at: str
    buckets: list[UsageLimitBucket]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_provider_usage_limits(provider: ProviderConfig) -> ProviderUsageLimits:
    status = get_provider_auth_status(
        provider_kind=provider.kind,
        provider_id=provider.id,
        auth_mode=provider.auth_mode,
    )
    if status.session_status != AUTH_SESSION_STATUS_CONNECTED:
        raise ConfigError(
            f"Provider '{provider.id}' does not have a connected subscription auth session."
        )
    session = load_auth_session(provider.id)
    if session is None:
        raise ConfigError(f"No auth session is stored for provider '{provider.id}'.")

    if provider.kind == "chatgpt" and provider.auth_mode == AUTH_MODE_CHATGPT_ACCOUNT:
        auth = OpenAIChatGPTAuthBackend().build_request_auth(
            request_url=_chatgpt_usage_url(provider),
            session=session,
        )
        payload = _get_json(
            auth.request_url, auth.headers, action="ChatGPT usage limits"
        )
        return _chatgpt_usage_limits(provider, payload, status.email, status.plan_type)

    if (
        provider.kind == "github_copilot"
        and provider.auth_mode == AUTH_MODE_COPILOT_ACCOUNT
    ):
        auth = GitHubCopilotAuthBackend().build_request_auth(
            request_url=GITHUB_COPILOT_USAGE_URL,
            session=session,
        )
        payload = _get_json(
            auth.request_url, auth.headers, action="GitHub Copilot usage limits"
        )
        return _copilot_usage_limits(provider, payload, status.email, status.plan_type)

    raise ConfigError(
        f"Provider '{provider.id}' does not support subscription usage limits."
    )


def _chatgpt_usage_url(provider: ProviderConfig) -> str:
    responses_url = (provider.responses_url or OPENAI_CHATGPT_RESPONSES_URL).rstrip("/")
    backend_api_marker = "/backend-api"
    if backend_api_marker in responses_url:
        base_url = responses_url.split(backend_api_marker, maxsplit=1)[0]
        return f"{base_url}{backend_api_marker}/wham/usage"
    if responses_url.endswith("/responses"):
        return f"{responses_url.removesuffix('/responses')}/usage"
    return CHATGPT_CODEX_USAGE_URL


def _get_json(url: str, headers: dict[str, str], *, action: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "pbi-agent",
            **headers,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_USAGE_TIMEOUT_SECS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{action} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{action} failed: {exc.reason}") from exc
    parsed = json.loads(body or "{}")
    if not isinstance(parsed, dict):
        raise ValueError(f"{action} returned a non-object JSON payload.")
    return parsed


def _chatgpt_usage_limits(
    provider: ProviderConfig,
    payload: dict[str, Any],
    account_label: str | None,
    stored_plan_type: str | None,
) -> ProviderUsageLimits:
    plan_type = _string_value(payload.get("plan_type")) or stored_plan_type
    buckets = [
        _chatgpt_bucket(
            "codex",
            "Codex",
            _object_value(payload.get("rate_limit")),
            _object_value(payload.get("credits")),
            _rate_limit_reached_type(payload.get("rate_limit_reached_type")),
        )
    ]
    additional = payload.get("additional_rate_limits")
    if isinstance(additional, list):
        for item in additional:
            if not isinstance(item, dict):
                continue
            limit_id = _string_value(item.get("metered_feature")) or "additional"
            label = _string_value(item.get("limit_name")) or _humanize(limit_id)
            buckets.append(
                _chatgpt_bucket(
                    limit_id,
                    label,
                    _object_value(item.get("rate_limit")),
                    None,
                    None,
                )
            )
    return ProviderUsageLimits(
        provider_id=provider.id,
        provider_kind=provider.kind,
        account_label=account_label,
        plan_type=plan_type,
        fetched_at=_now_iso(),
        buckets=buckets,
    )


def _chatgpt_bucket(
    bucket_id: str,
    label: str,
    rate_limit: dict[str, Any] | None,
    credits: dict[str, Any] | None,
    reached_type: str | None,
) -> UsageLimitBucket:
    windows: list[UsageLimitWindow] = []
    if rate_limit:
        for key, fallback_name in (
            ("primary_window", "5h"),
            ("secondary_window", "weekly"),
        ):
            window = _object_value(rate_limit.get(key))
            if window is None:
                continue
            used_percent = _float_value(window.get("used_percent"))
            window_minutes = _window_minutes(window.get("limit_window_seconds"))
            windows.append(
                UsageLimitWindow(
                    name=_window_duration_label(window_minutes, fallback_name),
                    used_percent=used_percent,
                    remaining_percent=_remaining_from_used_percent(used_percent),
                    window_minutes=window_minutes,
                    resets_at=_int_value(window.get("reset_at")),
                )
            )
    bucket = UsageLimitBucket(
        id=bucket_id,
        label=label,
        credits=_chatgpt_credits(credits),
        windows=windows,
    )
    bucket.status = "exhausted" if reached_type else _bucket_status(bucket)
    return bucket


def _chatgpt_credits(credits: dict[str, Any] | None) -> UsageLimitCredits | None:
    if not credits:
        return None
    return UsageLimitCredits(
        has_credits=_bool_value(credits.get("has_credits")),
        unlimited=_bool_value(credits.get("unlimited")),
        balance=_string_value(credits.get("balance")),
    )


def _copilot_usage_limits(
    provider: ProviderConfig,
    payload: dict[str, Any],
    account_label: str | None,
    stored_plan_type: str | None,
) -> ProviderUsageLimits:
    plan_type = (
        _string_value(payload.get("copilot_plan"))
        or _string_value(payload.get("access_type_sku"))
        or stored_plan_type
    )
    reset_at_iso = (
        _string_value(payload.get("quota_reset_date_utc"))
        or _string_value(payload.get("quota_reset_date"))
        or _string_value(payload.get("limited_user_reset_date"))
    )
    buckets = _copilot_snapshot_buckets(payload, reset_at_iso)
    if not buckets:
        buckets = _copilot_legacy_buckets(payload, reset_at_iso)
    return ProviderUsageLimits(
        provider_id=provider.id,
        provider_kind=provider.kind,
        account_label=account_label or _string_value(payload.get("login")),
        plan_type=plan_type,
        fetched_at=_now_iso(),
        buckets=buckets,
    )


def _copilot_snapshot_buckets(
    payload: dict[str, Any], reset_at_iso: str | None
) -> list[UsageLimitBucket]:
    labels = {
        "chat": "Chat messages",
        "premium_interactions": "Premium requests",
        "completions": "Inline suggestions",
    }
    snapshots = _object_value(payload.get("quota_snapshots"))
    if not snapshots:
        return []
    buckets: list[UsageLimitBucket] = []
    for key, label in labels.items():
        snapshot = _object_value(snapshots.get(key))
        if snapshot is None:
            continue
        total = _int_value(snapshot.get("entitlement"))
        remaining = _int_value(snapshot.get("remaining"))
        remaining_percent = _clamp_percent(
            _float_value(snapshot.get("percent_remaining"))
        )
        used_percent = None if remaining_percent is None else 100 - remaining_percent
        used = (
            total - remaining if total is not None and remaining is not None else None
        )
        bucket = UsageLimitBucket(
            id=key,
            label=label,
            unlimited=bool(_bool_value(snapshot.get("unlimited"))),
            overage_allowed=bool(_bool_value(snapshot.get("overage_permitted"))),
            overage_count=_int_value(snapshot.get("overage_count")) or 0,
            windows=[
                UsageLimitWindow(
                    name="monthly",
                    used_percent=used_percent,
                    remaining_percent=remaining_percent,
                    reset_at_iso=reset_at_iso,
                    used_requests=used,
                    total_requests=total,
                    remaining_requests=remaining,
                )
            ],
        )
        bucket.status = _bucket_status(bucket)
        buckets.append(bucket)
    return buckets


def _copilot_legacy_buckets(
    payload: dict[str, Any], reset_at_iso: str | None
) -> list[UsageLimitBucket]:
    limited = _object_value(payload.get("limited_user_quotas")) or {}
    monthly = _object_value(payload.get("monthly_quotas")) or {}
    labels = {"chat": "Chat messages", "completions": "Inline suggestions"}
    buckets: list[UsageLimitBucket] = []
    for key, label in labels.items():
        total = _int_value(monthly.get(key))
        remaining = _int_value(limited.get(key))
        if total is None or remaining is None:
            continue
        remaining_percent = _clamp_percent((remaining / total) * 100 if total else 0)
        used_percent = None if remaining_percent is None else 100 - remaining_percent
        bucket = UsageLimitBucket(
            id=key,
            label=label,
            windows=[
                UsageLimitWindow(
                    name="monthly",
                    used_percent=used_percent,
                    remaining_percent=remaining_percent,
                    reset_at_iso=reset_at_iso,
                    used_requests=total - remaining,
                    total_requests=total,
                    remaining_requests=remaining,
                )
            ],
        )
        bucket.status = _bucket_status(bucket)
        buckets.append(bucket)
    return buckets


def _bucket_status(bucket: UsageLimitBucket) -> str:
    if bucket.unlimited or (bucket.credits and bucket.credits.unlimited):
        return "ok"
    saw_data = False
    warning = False
    for window in bucket.windows:
        if window.remaining_percent is not None:
            saw_data = True
            if window.remaining_percent <= 0:
                return "exhausted"
            if window.remaining_percent <= 25:
                warning = True
        if window.used_percent is not None:
            saw_data = True
            if window.used_percent >= 100:
                return "exhausted"
            if window.used_percent >= 75:
                warning = True
        if window.remaining_requests is not None:
            saw_data = True
            if window.remaining_requests <= 0:
                return "exhausted"
    if warning:
        return "warning"
    return "ok" if saw_data else "unknown"


def _rate_limit_reached_type(value: object) -> str | None:
    obj = _object_value(value)
    if obj is None:
        return None
    return _string_value(obj.get("type")) or _string_value(obj.get("kind"))


def _object_value(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _remaining_from_used_percent(used_percent: float | None) -> float | None:
    if used_percent is None:
        return None
    return _clamp_percent(100 - used_percent)


def _clamp_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return min(100.0, max(0.0, value))


def _window_minutes(value: object) -> int | None:
    seconds = _int_value(value)
    if seconds is None:
        return None
    return max(int(seconds / 60), 1)


def _window_duration_label(minutes: int | None, fallback: str) -> str:
    if minutes is None:
        return fallback
    minutes = max(minutes, 0)
    minutes_per_hour = 60
    minutes_per_day = 24 * minutes_per_hour
    minutes_per_week = 7 * minutes_per_day
    minutes_per_month = 30 * minutes_per_day
    rounding_bias_minutes = 3
    if minutes <= minutes_per_day + rounding_bias_minutes:
        hours = max(1, int((minutes + rounding_bias_minutes) / minutes_per_hour))
        return f"{hours}h"
    if minutes <= minutes_per_week + rounding_bias_minutes:
        return "weekly"
    if minutes <= minutes_per_month + rounding_bias_minutes:
        return "monthly"
    return "annual"


def _humanize(value: str) -> str:
    return " ".join(
        part.capitalize() for part in value.replace("-", "_").split("_") if part
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "CHATGPT_CODEX_USAGE_URL",
    "GITHUB_COPILOT_BACKEND_ID",
    "GITHUB_COPILOT_USAGE_URL",
    "OPENAI_CHATGPT_BACKEND_ID",
    "ProviderUsageLimits",
    "UsageLimitBucket",
    "UsageLimitCredits",
    "UsageLimitWindow",
    "get_provider_usage_limits",
]
