from __future__ import annotations

import json
import re
from dataclasses import dataclass
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


@dataclass(slots=True)
class _StructuredErrorInfo:
    error_type: str | None = None
    message: str = ""
    request_id: str | None = None


def format_user_facing_error(exc: BaseException) -> str:
    raw_message = _normalize_whitespace(str(exc).strip())
    if not raw_message:
        return f"{exc.__class__.__name__}."

    structured = _extract_structured_error(raw_message)
    detail = _normalize_whitespace(structured.message)
    error_type = (structured.error_type or "").lower()
    request_id = structured.request_id

    if error_type == "overloaded_error" or "overloaded" in raw_message.lower():
        parts = ["Provider overloaded."]
        _append_detail(
            parts,
            detail,
            ignored={"overloaded", "the api is temporarily overloaded."},
        )
        parts.append("Retry shortly.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "resource_exhausted":
        parts = ["Rate limit reached."]
        _append_detail(parts, detail)
        parts.append("Check Gemini API rate limits or request a quota increase.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "rate_limit_error" or "rate limit" in raw_message.lower():
        parts = ["Rate limit reached."]
        _append_detail(parts, detail)
        parts.append("Retry shortly or switch model/provider.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "failed_precondition":
        parts = ["Request cannot be served in the current project or region."]
        _append_detail(parts, detail)
        parts.append(
            "If Gemini free tier is unavailable in your region, enable billing in Google AI Studio."
        )
        return _finalize_message(parts, request_id=request_id)

    if _contains_phrase(raw_message, detail, _UNRECOGNIZED_CHAT_MESSAGE):
        return _finalize_message(
            [
                "Provider rejected the tool follow-up request.",
                _preferred_detail(raw_message, detail, _UNRECOGNIZED_CHAT_MESSAGE),
                "This model/provider combination may not support the current tool-call transcript.",
            ],
            request_id=request_id,
        )

    if _contains_phrase(raw_message, detail, _MODEL_UNAVAILABLE_MESSAGE):
        return _finalize_message(
            [
                "Selected model is not available through the configured provider.",
                _preferred_detail(raw_message, detail, _MODEL_UNAVAILABLE_MESSAGE),
                "Choose a model/provider combination that is available on your gateway.",
            ],
            request_id=request_id,
        )

    if error_type == "authentication_error":
        parts = ["Authentication failed."]
        _append_detail(
            parts,
            detail,
            ignored={"there's an issue with your api key."},
        )
        parts.append("Check the configured API key.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "permission_error":
        parts = ["Permission denied."]
        _append_detail(
            parts,
            detail,
            ignored={
                "your api key does not have permission to use the specified resource."
            },
        )
        parts.append("Check that the API key can access the requested resource.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "permission_denied":
        parts = ["Permission denied."]
        _append_detail(parts, detail)
        parts.append("Check the Gemini API key permissions and model access.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "not_found_error":
        parts = ["Requested resource was not found."]
        _append_detail(
            parts,
            detail,
            ignored={"the requested resource could not be found."},
        )
        return _finalize_message(parts, request_id=request_id)

    if error_type == "not_found":
        parts = ["Requested resource was not found."]
        _append_detail(parts, detail)
        parts.append(
            "Check the request resource identifiers, model name, and API version."
        )
        return _finalize_message(parts, request_id=request_id)

    if error_type == "request_too_large":
        parts = ["Request is too large."]
        _append_detail(
            parts,
            detail,
            ignored={"request exceeds the maximum allowed number of bytes."},
        )
        parts.append("Reduce the Anthropic Messages API request size below 32 MB.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "invalid_request_error":
        parts = ["Invalid request."]
        _append_detail(
            parts,
            detail,
            ignored={"there was an issue with the format or content of your request."},
        )
        parts.append("Check the request payload, selected model, and tool transcript.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "invalid_argument":
        parts = ["Invalid request."]
        _append_detail(parts, detail)
        parts.append("Check Gemini request fields, model parameters, and API version.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "api_error":
        parts = ["Provider error."]
        _append_detail(
            parts,
            detail,
            ignored={
                "an unexpected error has occurred internal to anthropic's systems."
            },
        )
        parts.append("Retry shortly.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "internal":
        parts = ["Provider error."]
        _append_detail(parts, detail)
        parts.append(
            "Reduce the prompt/context size or retry with another Gemini model."
        )
        return _finalize_message(parts, request_id=request_id)

    if error_type == "unavailable":
        parts = ["Provider overloaded."]
        _append_detail(parts, detail)
        parts.append("Retry shortly or switch to another Gemini model.")
        return _finalize_message(parts, request_id=request_id)

    if error_type == "deadline_exceeded":
        parts = ["Request timed out."]
        _append_detail(parts, detail)
        parts.append("Increase the client timeout or reduce the prompt/context size.")
        return _finalize_message(parts, request_id=request_id)

    if "api key was reported as leaked" in raw_message.lower() or (
        detail and "api key was reported as leaked" in detail.lower()
    ):
        return _finalize_message(
            [
                "Authentication failed.",
                "Gemini rejected an API key that was reported as leaked.",
                "Generate a new API key in Google AI Studio and replace the blocked key.",
            ],
            request_id=request_id,
        )

    if detail and detail != raw_message:
        return _finalize_message(["Request failed.", detail], request_id=request_id)

    return _finalize_message([raw_message], request_id=request_id)


def _extract_structured_error(message: str) -> _StructuredErrorInfo:
    payload = _parse_embedded_json(message)
    if payload is None:
        return _StructuredErrorInfo(message=message)

    request_id = payload.get("request_id")
    error_type: str | None = None
    detail = ""

    error_value = payload.get("error")
    if isinstance(error_value, dict):
        payload_type = error_value.get("type")
        if isinstance(payload_type, str) and payload_type.strip():
            error_type = payload_type.strip()
        elif (
            isinstance(error_value.get("status"), str)
            and error_value.get("status").strip()
        ):
            error_type = error_value.get("status").strip().lower()
        payload_message = error_value.get("message")
        if isinstance(payload_message, str) and payload_message.strip():
            detail = payload_message.strip()
    elif isinstance(error_value, str) and error_value.strip():
        detail = error_value.strip()

    if not detail:
        detail = _extract_from_payload(payload) or message

    return _StructuredErrorInfo(
        error_type=error_type,
        message=detail,
        request_id=request_id.strip()
        if isinstance(request_id, str) and request_id.strip()
        else None,
    )


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
        if isinstance(error_value, str):
            candidates.append(error_value)
        elif error_value is not None and error_value is not value:
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


def _append_detail(
    parts: list[str],
    detail: str,
    *,
    ignored: set[str] | None = None,
) -> None:
    normalized = _normalize_whitespace(detail)
    if not normalized:
        return
    if normalized == parts[0]:
        return
    if ignored and normalized.lower() in ignored:
        return
    parts.append(normalized)


def _finalize_message(parts: list[str], *, request_id: str | None) -> str:
    final_parts = [part for part in parts if part]
    if request_id:
        request_line = f"Request ID: {request_id}"
        if request_line not in final_parts:
            final_parts.append(request_line)
    return "\n".join(final_parts)
