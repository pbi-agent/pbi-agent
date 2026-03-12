from __future__ import annotations

import json

import pytest

from pbi_agent.agent.error_formatting import format_user_facing_error


def test_format_user_facing_error_preserves_overloaded_as_non_rate_limit() -> None:
    message = (
        "Anthropic API overloaded after 2 attempts: "
        '{"type":"error","error":{"message":"Overloaded"}}'
    )

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == "Provider overloaded.\nRetry shortly."


def test_format_user_facing_error_handles_string_overload_payload() -> None:
    message = 'Anthropic API overloaded after 2 attempts: {"error":"overloaded"}'

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == "Provider overloaded.\nRetry shortly."


def test_format_user_facing_error_keeps_rate_limit_message() -> None:
    message = (
        "Anthropic rate limit exceeded after 2 attempts: "
        '{"type":"error","error":{"message":"Too many requests"}}'
    )

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == (
        "Rate limit reached.\nToo many requests\nRetry shortly or switch model/provider."
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Prefilling assistant messages is not supported for this model.",
                },
                "request_id": "req_invalid",
            },
            (
                "Invalid request.\n"
                "Prefilling assistant messages is not supported for this model.\n"
                "Check the request payload, selected model, and tool transcript.\n"
                "Request ID: req_invalid"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "There's an issue with your API key.",
                },
                "request_id": "req_auth",
            },
            (
                "Authentication failed.\n"
                "Check the configured API key.\n"
                "Request ID: req_auth"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "type": "permission_error",
                    "message": (
                        "Your API key does not have permission to use the specified "
                        "resource."
                    ),
                },
                "request_id": "req_perm",
            },
            (
                "Permission denied.\n"
                "Check that the API key can access the requested resource.\n"
                "Request ID: req_perm"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "type": "not_found_error",
                    "message": "The requested resource could not be found.",
                },
                "request_id": "req_missing",
            },
            "Requested resource was not found.\nRequest ID: req_missing",
        ),
        (
            {
                "type": "error",
                "error": {
                    "type": "request_too_large",
                    "message": "Request exceeds the maximum allowed number of bytes.",
                },
                "request_id": "req_large",
            },
            (
                "Request is too large.\n"
                "Reduce the Anthropic Messages API request size below 32 MB.\n"
                "Request ID: req_large"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": "An unexpected error has occurred internal to Anthropic's systems.",
                },
                "request_id": "req_api",
            },
            "Provider error.\nRetry shortly.\nRequest ID: req_api",
        ),
    ],
)
def test_format_user_facing_error_handles_documented_anthropic_error_types(
    payload: dict[str, object],
    expected: str,
) -> None:
    message = f"Anthropic API error: {json.dumps(payload)}"

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "type": "error",
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": "The request body is malformed.",
                },
                "request_id": "req_gemini_invalid",
            },
            (
                "Invalid request.\n"
                "The request body is malformed.\n"
                "Check Gemini request fields, model parameters, and API version.\n"
                "Request ID: req_gemini_invalid"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "status": "FAILED_PRECONDITION",
                    "message": (
                        "Gemini API free tier is not available in your country. "
                        "Please enable billing on your project in Google AI Studio."
                    ),
                },
                "request_id": "req_gemini_precondition",
            },
            (
                "Request cannot be served in the current project or region.\n"
                "Gemini API free tier is not available in your country. Please "
                "enable billing on your project in Google AI Studio.\n"
                "If Gemini free tier is unavailable in your region, enable billing "
                "in Google AI Studio.\n"
                "Request ID: req_gemini_precondition"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "You've exceeded the rate limit.",
                },
                "request_id": "req_gemini_rl",
            },
            (
                "Rate limit reached.\n"
                "You've exceeded the rate limit.\n"
                "Check Gemini API rate limits or request a quota increase.\n"
                "Request ID: req_gemini_rl"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "status": "UNAVAILABLE",
                    "message": "The service is temporarily running out of capacity.",
                },
                "request_id": "req_gemini_unavailable",
            },
            (
                "Provider overloaded.\n"
                "The service is temporarily running out of capacity.\n"
                "Retry shortly or switch to another Gemini model.\n"
                "Request ID: req_gemini_unavailable"
            ),
        ),
        (
            {
                "type": "error",
                "error": {
                    "status": "DEADLINE_EXCEEDED",
                    "message": (
                        "The service is unable to finish processing within the deadline."
                    ),
                },
                "request_id": "req_gemini_deadline",
            },
            (
                "Request timed out.\n"
                "The service is unable to finish processing within the deadline.\n"
                "Increase the client timeout or reduce the prompt/context size.\n"
                "Request ID: req_gemini_deadline"
            ),
        ),
    ],
)
def test_format_user_facing_error_handles_gemini_status_codes_in_anthropic_shape(
    payload: dict[str, object],
    expected: str,
) -> None:
    message = f"Anthropic API error: {json.dumps(payload)}"

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == expected


def test_format_user_facing_error_handles_leaked_gemini_api_key_message() -> None:
    message = (
        "Anthropic API error 403: "
        '{"error":{"message":"Your API key was reported as leaked. Please use '
        'another API key."}}'
    )

    formatted = format_user_facing_error(RuntimeError(message))

    assert formatted == (
        "Authentication failed.\n"
        "Gemini rejected an API key that was reported as leaked.\n"
        "Generate a new API key in Google AI Studio and replace the blocked key."
    )
