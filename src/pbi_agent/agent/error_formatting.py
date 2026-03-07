from __future__ import annotations

import json
import re
from typing import Any

_GENERIC_ERROR_MESSAGES = {
    "provider returned error",
    "no error message",
}
_UNRECOGNIZED_CHAT_MESSAGE = "Unrecognized chat message."
_MODEL_UNAVAILABLE_MESSAGE = (
    "No allowed providers are available for the selected model."
)
_WHITESPACE_RE = re.compile(r"\s+")


def format_user_facing_error(exc: BaseException) -> str:
    raw_message = _normalize_whitespace(str(exc).strip())
    if not raw_message:
        return f"{exc.__class__.__name__}."

    detail = _extract_error_detail(raw_message)
    detail = _normalize_whitespace(detail)

    if "rate limit" in raw_message.lower():
        parts = ["Rate limit reached."]
        if detail:
            parts.append(detail)
        parts.append("Retry shortly or switch model/provider.")
        return "\n".join(parts)

    if _contains_phrase(raw_message, detail, _UNRECOGNIZED_CHAT_MESSAGE):
        return "\n".join(
            [
                "Provider rejected the tool follow-up request.",
                _preferred_detail(raw_message, detail, _UNRECOGNIZED_CHAT_MESSAGE),
                "This model/provider combination may not support the current tool-call transcript.",
            ]
        )

    if _contains_phrase(raw_message, detail, _MODEL_UNAVAILABLE_MESSAGE):
        return "\n".join(
            [
                "Selected model is not available through the configured provider.",
                _preferred_detail(raw_message, detail, _MODEL_UNAVAILABLE_MESSAGE),
                "Choose a model/provider combination that is available on your gateway.",
            ]
        )

    if detail and detail != raw_message:
        return "\n".join(["Request failed.", detail])

    return raw_message


def _extract_error_detail(message: str) -> str:
    payload = _parse_embedded_json(message)
    if payload is None:
        return message

    extracted = _extract_from_payload(payload)
    return extracted or message


def _parse_embedded_json(message: str) -> dict[str, Any] | None:
    start = message.find("{")
    if start < 0:
        return None
    try:
        payload = json.loads(message[start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_from_payload(payload: dict[str, Any]) -> str:
    candidates: list[str] = []
    _collect_candidate_messages(payload, candidates)

    seen: set[str] = set()
    filtered: list[str] = []
    for candidate in candidates:
        normalized = _normalize_whitespace(candidate)
        if not normalized:
            continue
        if normalized.lower() in _GENERIC_ERROR_MESSAGES:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)

    return "\n".join(filtered[:2])


def _collect_candidate_messages(value: Any, candidates: list[str]) -> None:
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, str):
            candidates.append(message)

        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            raw_value = metadata.get("raw")
            if isinstance(raw_value, str):
                parsed_raw = _parse_nested_json_string(raw_value)
                if parsed_raw is not None:
                    _collect_candidate_messages(parsed_raw, candidates)
                else:
                    candidates.append(raw_value)

            available = metadata.get("available_providers")
            if isinstance(available, list) and available:
                providers = ", ".join(str(item) for item in available if str(item))
                if providers:
                    candidates.append(f"Available providers: {providers}.")

        error_value = value.get("error")
        if error_value is not None and error_value is not value:
            _collect_candidate_messages(error_value, candidates)
        return

    if isinstance(value, list):
        for item in value:
            _collect_candidate_messages(item, candidates)


def _parse_nested_json_string(raw_value: str) -> dict[str, Any] | None:
    stripped = raw_value.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _contains_phrase(raw_message: str, detail: str, phrase: str) -> bool:
    lowered_phrase = phrase.lower()
    return lowered_phrase in raw_message.lower() or lowered_phrase in detail.lower()


def _preferred_detail(raw_message: str, detail: str, phrase: str) -> str:
    return phrase if phrase.lower() in raw_message.lower() else detail
