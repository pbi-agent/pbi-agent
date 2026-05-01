from __future__ import annotations

from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.auth.usage_limits import (
    _chatgpt_usage_limits,
    _chatgpt_usage_url,
    _copilot_usage_limits,
)
from pbi_agent.config import ProviderConfig


def test_chatgpt_usage_url_uses_wham_endpoint_for_default_backend_api() -> None:
    provider = ProviderConfig(
        id="chatgpt-main",
        name="ChatGPT",
        kind="chatgpt",
        auth_mode="chatgpt_account",
        responses_url=OPENAI_CHATGPT_RESPONSES_URL,
    )

    assert _chatgpt_usage_url(provider) == "https://chatgpt.com/backend-api/wham/usage"


def test_chatgpt_usage_url_keeps_codex_style_non_backend_endpoint() -> None:
    provider = ProviderConfig(
        id="chatgpt-main",
        name="ChatGPT",
        kind="chatgpt",
        auth_mode="chatgpt_account",
        responses_url="https://codex.example.test/api/codex/responses",
    )

    assert _chatgpt_usage_url(provider) == "https://codex.example.test/api/codex/usage"


def test_chatgpt_usage_maps_primary_and_additional_limits() -> None:
    provider = ProviderConfig(
        id="chatgpt-main",
        name="ChatGPT",
        kind="chatgpt",
        auth_mode="chatgpt_account",
    )

    usage = _chatgpt_usage_limits(
        provider,
        {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {
                    "used_percent": 42,
                    "limit_window_seconds": 18_000,
                    "reset_at": 123,
                },
                "secondary_window": {
                    "used_percent": 84,
                    "limit_window_seconds": 604_800,
                    "reset_at": 456,
                },
            },
            "additional_rate_limits": [
                {
                    "limit_name": "codex_other",
                    "metered_feature": "codex_other",
                    "rate_limit": {
                        "primary_window": {
                            "used_percent": 70,
                            "limit_window_seconds": 900,
                            "reset_at": 789,
                        }
                    },
                }
            ],
            "credits": {"has_credits": True, "unlimited": False, "balance": "9.99"},
        },
        "user@example.com",
        None,
    )

    assert usage.provider_id == "chatgpt-main"
    assert usage.plan_type == "pro"
    assert usage.account_label == "user@example.com"
    assert len(usage.buckets) == 2
    assert usage.buckets[0].id == "codex"
    assert usage.buckets[0].status == "warning"
    assert usage.buckets[0].credits is not None
    assert usage.buckets[0].credits.balance == "9.99"
    assert usage.buckets[0].windows[0].name == "5h"
    assert usage.buckets[0].windows[0].used_percent == 42
    assert usage.buckets[0].windows[0].remaining_percent == 58
    assert usage.buckets[0].windows[0].window_minutes == 300
    assert usage.buckets[0].windows[1].name == "weekly"
    assert usage.buckets[0].windows[1].used_percent == 84
    assert usage.buckets[1].id == "codex_other"
    assert usage.buckets[1].label == "codex_other"


def test_chatgpt_usage_marks_type_rate_limit_reached_as_exhausted() -> None:
    provider = ProviderConfig(
        id="chatgpt-main",
        name="ChatGPT",
        kind="chatgpt",
        auth_mode="chatgpt_account",
    )

    usage = _chatgpt_usage_limits(
        provider,
        {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 10,
                    "limit_window_seconds": 300,
                    "reset_at": 123,
                }
            },
            "rate_limit_reached_type": {"type": "workspace_member_usage_limit_reached"},
        },
        None,
        None,
    )

    assert usage.buckets[0].status == "exhausted"


def test_copilot_usage_maps_quota_snapshots() -> None:
    provider = ProviderConfig(
        id="copilot-main",
        name="Copilot",
        kind="github_copilot",
        auth_mode="copilot_account",
    )

    usage = _copilot_usage_limits(
        provider,
        {
            "copilot_plan": "individual",
            "quota_reset_date_utc": "2026-06-01T00:00:00Z",
            "quota_snapshots": {
                "chat": {
                    "entitlement": 100,
                    "remaining": 25,
                    "percent_remaining": 25,
                    "overage_permitted": False,
                    "overage_count": 0,
                    "unlimited": False,
                },
                "premium_interactions": {
                    "entitlement": 50,
                    "remaining": 0,
                    "percent_remaining": 0,
                    "overage_permitted": True,
                    "overage_count": 2,
                    "unlimited": False,
                },
            },
        },
        None,
        None,
    )

    assert usage.plan_type == "individual"
    assert len(usage.buckets) == 2
    assert usage.buckets[0].id == "chat"
    assert usage.buckets[0].status == "warning"
    assert usage.buckets[0].windows[0].used_requests == 75
    assert usage.buckets[0].windows[0].remaining_requests == 25
    assert usage.buckets[1].id == "premium_interactions"
    assert usage.buckets[1].status == "exhausted"
    assert usage.buckets[1].overage_allowed is True
    assert usage.buckets[1].overage_count == 2


def test_copilot_usage_maps_legacy_quotas() -> None:
    provider = ProviderConfig(
        id="copilot-main",
        name="Copilot",
        kind="github_copilot",
        auth_mode="copilot_account",
    )

    usage = _copilot_usage_limits(
        provider,
        {
            "access_type_sku": "free",
            "limited_user_reset_date": "2026-06-01",
            "monthly_quotas": {"chat": 50, "completions": 100},
            "limited_user_quotas": {"chat": 10, "completions": 100},
        },
        None,
        None,
    )

    assert usage.plan_type == "free"
    assert [bucket.id for bucket in usage.buckets] == ["chat", "completions"]
    assert usage.buckets[0].windows[0].used_percent == 80
    assert usage.buckets[0].status == "warning"
    assert usage.buckets[1].windows[0].remaining_percent == 100
    assert usage.buckets[1].status == "ok"
