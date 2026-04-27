from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from pbi_agent import __version__
from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.auth.service import build_runtime_request_auth, refresh_runtime_auth
from pbi_agent.config import ConfigError, Settings, missing_api_key_message
from pbi_agent.providers.anthropic_provider import ANTHROPIC_VERSION
from pbi_agent.providers.chatgpt_codex_backend import chatgpt_user_agent
from pbi_agent.providers.github_copilot_backend import GITHUB_COPILOT_MODELS_URL

_DISCOVERY_TIMEOUT_SECS = 30.0
_SUPPORTED_DISCOVERY_PROVIDERS = frozenset(
    {
        "openai",
        "azure",
        "chatgpt",
        "github_copilot",
        "xai",
        "google",
        "anthropic",
        "generic",
    }
)
_OPENAI_CHATGPT_MIN_CLIENT_VERSION = "0.124.0"
_MANUAL_ENTRY_ONLY_REASONS: dict[str, str] = {}


@dataclass(slots=True)
class ProviderModelDiscoveryError:
    code: str
    message: str
    status_code: int | None = None


@dataclass(slots=True)
class DiscoveredProviderModel:
    id: str
    display_name: str | None = None
    created: int | str | None = None
    owned_by: str | None = None
    input_modalities: list[str] = field(default_factory=list)
    output_modalities: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    supports_reasoning_effort: bool | None = None


@dataclass(slots=True)
class ProviderModelDiscoveryResult:
    provider_kind: str
    discovery_supported: bool
    manual_entry_required: bool
    models: list[DiscoveredProviderModel]
    error: ProviderModelDiscoveryError | None = None


def discover_provider_models(settings: Settings) -> ProviderModelDiscoveryResult:
    provider_kind = settings.provider
    if provider_kind not in _SUPPORTED_DISCOVERY_PROVIDERS:
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=False,
            manual_entry_required=True,
            models=[],
            error=None,
        )

    # Azure requires user-configured deployment names; skip discovery before
    # checking auth so Settings can always show manual entry.
    if provider_kind == "azure":
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=False,
            manual_entry_required=True,
            models=[],
            error=None,
        )

    auth_error = _missing_auth_error(settings)
    if auth_error is not None:
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=True,
            manual_entry_required=True,
            models=[],
            error=auth_error,
        )

    try:
        if provider_kind in {"openai", "chatgpt"}:
            models = _discover_openai_models(settings)
        elif provider_kind == "github_copilot":
            models = _discover_github_copilot_models(settings)
        elif provider_kind == "xai":
            models = _discover_xai_models(settings)
        elif provider_kind == "google":
            models = _discover_google_models(settings)
        elif provider_kind == "generic":
            models = _discover_generic_models(settings)
        else:
            models = _discover_anthropic_models(settings)
    except urllib.error.HTTPError as exc:
        error_body = _read_error_body(exc)
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=True,
            manual_entry_required=True,
            models=[],
            error=ProviderModelDiscoveryError(
                code="http_error",
                message=_http_error_message(exc, error_body),
                status_code=exc.code,
            ),
        )
    except urllib.error.URLError as exc:
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=True,
            manual_entry_required=True,
            models=[],
            error=ProviderModelDiscoveryError(
                code="network_error",
                message=str(exc.reason or exc),
            ),
        )
    except ConfigError as exc:
        return ProviderModelDiscoveryResult(
            provider_kind=provider_kind,
            discovery_supported=True,
            manual_entry_required=True,
            models=[],
            error=ProviderModelDiscoveryError(
                code="config_error",
                message=str(exc),
            ),
        )

    return ProviderModelDiscoveryResult(
        provider_kind=provider_kind,
        discovery_supported=True,
        manual_entry_required=False,
        models=sorted(
            models,
            key=lambda item: ((item.display_name or item.id).lower(), item.id),
        ),
        error=None,
    )


def manual_entry_reason(provider_kind: str) -> str | None:
    return _MANUAL_ENTRY_ONLY_REASONS.get(provider_kind)


def _discover_openai_models(settings: Settings) -> list[DiscoveredProviderModel]:
    if settings.responses_url == OPENAI_CHATGPT_RESPONSES_URL:
        response = _get_json(settings, _openai_chatgpt_models_url())
        payload = response.get("models", [])
        if not isinstance(payload, list):
            return []
        return [
            DiscoveredProviderModel(
                id=model_id,
                display_name=_string_value(item.get("display_name")) or model_id,
                created=_created_value(item.get("created")),
                owned_by="openai",
                input_modalities=_string_list(item.get("input_modalities")),
                output_modalities=["text"],
                aliases=_string_list(item.get("aliases")),
                supports_reasoning_effort=_openai_chatgpt_supports_reasoning_effort(
                    item
                ),
            )
            for item in payload
            if isinstance(item, dict)
            if item.get("supported_in_api", True) is not False
            if _string_value(item.get("visibility")) != "hide"
            if (model_id := _string_value(item.get("slug")))
        ]

    response = _get_json(
        settings, _replace_path_suffix(settings.responses_url, "models")
    )
    payload = response.get("data", [])
    if not isinstance(payload, list):
        return []
    return [
        DiscoveredProviderModel(
            id=model_id,
            display_name=_string_value(item.get("display_name")) or model_id,
            created=_created_value(item.get("created")),
            owned_by=_string_value(item.get("owned_by")),
            input_modalities=_string_list(item.get("input_modalities")),
            output_modalities=_string_list(item.get("output_modalities")),
            aliases=_string_list(item.get("aliases")),
            supports_reasoning_effort=_openai_supports_reasoning_effort(model_id),
        )
        for item in payload
        if isinstance(item, dict)
        if (model_id := _string_value(item.get("id")))
    ]


def _discover_xai_models(settings: Settings) -> list[DiscoveredProviderModel]:
    response = _get_json(
        settings,
        _replace_path_suffix(settings.responses_url, "language-models"),
    )
    payload = response.get("models", [])
    if not isinstance(payload, list):
        return []
    return [
        DiscoveredProviderModel(
            id=model_id,
            display_name=_string_value(item.get("display_name")) or model_id,
            created=_created_value(item.get("created")),
            owned_by=_string_value(item.get("owned_by")),
            input_modalities=_string_list(item.get("input_modalities")),
            output_modalities=_string_list(item.get("output_modalities")),
            aliases=_string_list(item.get("aliases")),
            supports_reasoning_effort=_xai_supports_reasoning_effort(model_id),
        )
        for item in payload
        if isinstance(item, dict)
        if (model_id := _string_value(item.get("id")))
    ]


def _discover_github_copilot_models(
    settings: Settings,
) -> list[DiscoveredProviderModel]:
    response = _get_json(settings, GITHUB_COPILOT_MODELS_URL)
    payload = response.get("data", [])
    if not isinstance(payload, list):
        return []

    models: list[DiscoveredProviderModel] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        model_id = _string_value(item.get("id"))
        if not model_id:
            continue
        capabilities = item.get("capabilities")
        if not isinstance(capabilities, dict):
            continue
        if _string_value(capabilities.get("type")) != "chat":
            continue
        if item.get("model_picker_enabled", True) is False:
            continue
        policy = item.get("policy")
        if isinstance(policy, dict):
            policy_state = _string_value(policy.get("state"))
            if policy_state not in {None, "enabled"}:
                continue
        supports = item.get("capabilities", {}).get("supports", {})
        if not isinstance(supports, dict):
            supports = {}
        aliases = [
            alias
            for alias in [
                _string_value(capabilities.get("family")),
                _string_value(item.get("version")),
            ]
            if alias and alias != model_id
        ]
        input_modalities = ["text"]
        if _bool_value(supports.get("vision")):
            input_modalities.append("image")
        models.append(
            DiscoveredProviderModel(
                id=model_id,
                display_name=_string_value(item.get("name")) or model_id,
                created=None,
                owned_by=_string_value(item.get("vendor")),
                input_modalities=input_modalities,
                output_modalities=["text"],
                aliases=aliases,
                supports_reasoning_effort=_supports_reasoning_effort(
                    supports.get("reasoning_effort")
                ),
            )
        )
    return models


def _discover_generic_models(settings: Settings) -> list[DiscoveredProviderModel]:
    response = _get_json(settings, _generic_models_url(settings.generic_api_url))
    payload = response.get("data")
    if not isinstance(payload, list):
        raise ConfigError("Provider models endpoint returned an unexpected payload.")
    return [
        DiscoveredProviderModel(
            id=model_id,
            display_name=_string_value(item.get("display_name")) or model_id,
            created=_created_value(item.get("created")),
            owned_by=_string_value(item.get("owned_by")),
            input_modalities=_string_list(item.get("input_modalities")),
            output_modalities=_string_list(item.get("output_modalities")),
            aliases=_string_list(item.get("aliases")),
            supports_reasoning_effort=_openai_supports_reasoning_effort(model_id),
        )
        for item in payload
        if isinstance(item, dict)
        if (model_id := _string_value(item.get("id")))
    ]


def _discover_anthropic_models(settings: Settings) -> list[DiscoveredProviderModel]:
    url = (
        _replace_path_suffix(settings.responses_url, "models")
        if settings.provider == "azure"
        else "https://api.anthropic.com/v1/models"
    )
    models: list[DiscoveredProviderModel] = []
    after_id: str | None = None
    while True:
        page_url = _append_query_params(url, {"limit": "1000", "after_id": after_id})
        response = _get_json(
            settings,
            page_url,
            extra_headers={"anthropic-version": ANTHROPIC_VERSION},
            auth_header="x-api-key",
        )
        payload = response.get("data", [])
        if not isinstance(payload, list):
            break
        models.extend(
            DiscoveredProviderModel(
                id=model_id,
                display_name=_string_value(item.get("display_name")) or model_id,
                created=_string_value(item.get("created_at")),
                owned_by="anthropic",
                input_modalities=_anthropic_input_modalities(item),
                output_modalities=["text"],
                aliases=[],
                supports_reasoning_effort=_anthropic_supports_reasoning_effort(item),
            )
            for item in payload
            if isinstance(item, dict)
            if (model_id := _string_value(item.get("id")))
        )
        if not response.get("has_more"):
            break
        after_id = _string_value(response.get("last_id"))
        if not after_id:
            break
    return models


def _discover_google_models(settings: Settings) -> list[DiscoveredProviderModel]:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    models: list[DiscoveredProviderModel] = []
    page_token: str | None = None
    while True:
        page_url = _append_query_params(
            url,
            {"pageSize": "1000", "pageToken": page_token},
        )
        response = _get_json(
            settings,
            page_url,
            extra_headers={"x-goog-api-key": settings.api_key},
            auth_header="x-goog-api-key",
        )
        payload = response.get("models", [])
        if not isinstance(payload, list):
            break
        for item in payload:
            if not isinstance(item, dict):
                continue
            supported_methods = _string_list(item.get("supportedGenerationMethods"))
            if "generateContent" not in supported_methods:
                continue
            model_id = _string_value(item.get("baseModelId")) or _strip_models_prefix(
                _string_value(item.get("name"))
            )
            if not model_id:
                continue
            resource_name = _strip_models_prefix(_string_value(item.get("name")))
            aliases = [
                alias
                for alias in [resource_name, _string_value(item.get("version"))]
                if alias and alias != model_id
            ]
            models.append(
                DiscoveredProviderModel(
                    id=model_id,
                    display_name=_string_value(item.get("displayName")) or model_id,
                    created=None,
                    owned_by="google",
                    input_modalities=[],
                    output_modalities=["text"],
                    aliases=aliases,
                    supports_reasoning_effort=_bool_value(item.get("thinking")),
                )
            )
        page_token = _string_value(response.get("nextPageToken"))
        if not page_token:
            break
    return models


def _get_json(
    settings: Settings,
    url: str,
    *,
    extra_headers: dict[str, str] | None = None,
    auth_header: str = "Authorization",
) -> dict[str, Any]:
    retried_unauthorized_refresh = False
    while True:
        request_auth = build_runtime_request_auth(
            provider_kind=settings.provider,
            request_url=url,
            auth=settings.auth,
        )
        headers = _request_headers(
            settings,
            request_auth_headers=request_auth.headers,
            extra_headers=extra_headers,
            auth_header=auth_header,
        )
        request = urllib.request.Request(
            request_auth.request_url,
            headers=headers,
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=_DISCOVERY_TIMEOUT_SECS
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if (
                exc.code == 401
                and not retried_unauthorized_refresh
                and settings.provider in {"openai", "azure", "chatgpt"}
                and isinstance(settings.auth, OAuthSessionAuth)
            ):
                settings.auth = refresh_runtime_auth(
                    provider_kind=settings.provider,
                    auth=settings.auth,
                )
                retried_unauthorized_refresh = True
                continue
            raise
        if not isinstance(payload, dict):
            raise ConfigError(
                "Provider models endpoint returned an unexpected payload."
            )
        return payload


def _request_headers(
    settings: Settings,
    *,
    request_auth_headers: dict[str, str],
    extra_headers: dict[str, str] | None,
    auth_header: str,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
    }
    if settings.responses_url == OPENAI_CHATGPT_RESPONSES_URL:
        headers["originator"] = "opencode"
        headers["User-Agent"] = chatgpt_user_agent()

    if auth_header == "Authorization":
        headers.update(request_auth_headers)
    else:
        authorization = request_auth_headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            headers[auth_header] = authorization[len("Bearer ") :]
        for key, value in request_auth_headers.items():
            if key != "Authorization":
                headers[key] = value

    if extra_headers:
        headers.update(extra_headers)
    return headers


def _openai_chatgpt_models_url() -> str:
    return _append_query_params(
        _replace_path_suffix(OPENAI_CHATGPT_RESPONSES_URL, "models"),
        {"client_version": _openai_chatgpt_client_version()},
    )


def _generic_models_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts[-2:] == ["chat", "completions"]:
        path_parts = [*path_parts[:-2], "models"]
    elif path_parts:
        path_parts[-1] = "models"
    else:
        path_parts = ["models"]
    return parsed._replace(path="/" + "/".join(path_parts), query="").geturl()


def _replace_path_suffix(url: str, replacement: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        path_parts[-1] = replacement
    else:
        path_parts = [replacement]
    return parsed._replace(path="/" + "/".join(path_parts), query="").geturl()


def _append_query_params(url: str, params: dict[str, str | None]) -> str:
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value is not None}
    )
    parsed = urllib.parse.urlparse(url)
    return parsed._replace(query=query).geturl()


def _missing_auth_error(settings: Settings) -> ProviderModelDiscoveryError | None:
    if settings.provider in {"openai", "azure"}:
        if settings.auth is None:
            return ProviderModelDiscoveryError(
                code="auth_required",
                message=missing_api_key_message(settings.provider),
            )
        return None
    if settings.provider == "chatgpt":
        if settings.auth is None:
            return ProviderModelDiscoveryError(
                code="auth_required",
                message=(
                    "Missing authentication for provider 'chatgpt'. "
                    "Connect a ChatGPT account session first."
                ),
            )
        return None
    if settings.provider == "github_copilot":
        if settings.auth is None:
            return ProviderModelDiscoveryError(
                code="auth_required",
                message=(
                    "Missing authentication for provider 'github_copilot'. "
                    "Connect a GitHub Copilot account session first."
                ),
            )
        return None
    if not settings.api_key:
        return ProviderModelDiscoveryError(
            code="auth_required",
            message=missing_api_key_message(settings.provider),
        )
    return None


def _http_error_message(exc: urllib.error.HTTPError, error_body: str) -> str:
    try:
        payload = json.loads(error_body) if error_body else {}
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = _string_value(error.get("message"))
            if message:
                return message
        message = _string_value(payload.get("message")) or _string_value(
            payload.get("detail")
        )
        if message:
            return message
    body = error_body.strip()
    if body:
        return f"Provider models request failed ({exc.code}): {body}"
    return f"Provider models request failed with status {exc.code}."


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except Exception:
        return ""


def _whole_version(version: str) -> str:
    return version.split("-", 1)[0]


def _openai_chatgpt_client_version() -> str:
    return _max_semver(
        _whole_version(__version__),
        _OPENAI_CHATGPT_MIN_CLIENT_VERSION,
    )


def _max_semver(*versions: str) -> str:
    best = versions[0]
    best_parts = _semver_parts(best)
    for candidate in versions[1:]:
        candidate_parts = _semver_parts(candidate)
        if candidate_parts > best_parts:
            best = candidate
            best_parts = candidate_parts
    return best


def _semver_parts(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    numbers: list[int] = []
    for index in range(3):
        try:
            numbers.append(int(parts[index]))
        except (IndexError, ValueError):
            numbers.append(0)
    return (numbers[0], numbers[1], numbers[2])


def _string_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _openai_chatgpt_supports_reasoning_effort(item: dict[str, Any]) -> bool | None:
    supported_levels = item.get("supported_reasoning_levels")
    if isinstance(supported_levels, list):
        return bool(supported_levels)
    return _bool_value(item.get("supports_reasoning_summaries"))


def _supports_reasoning_effort(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return bool(_string_list(value))
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _string_value(item)
        if text:
            items.append(text)
    return items


def _created_value(value: Any) -> int | str | None:
    if isinstance(value, int):
        return value
    return _string_value(value)


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _anthropic_supports_reasoning_effort(item: dict[str, Any]) -> bool | None:
    capabilities = item.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    effort = capabilities.get("effort")
    if not isinstance(effort, dict):
        return None
    return _bool_value(effort.get("supported"))


def _anthropic_input_modalities(item: dict[str, Any]) -> list[str]:
    modalities = ["text"]
    capabilities = item.get("capabilities")
    if not isinstance(capabilities, dict):
        return modalities
    image_input = capabilities.get("image_input")
    if _capability_supported(image_input):
        modalities.append("image")
    pdf_input = capabilities.get("pdf_input")
    if _capability_supported(pdf_input):
        modalities.append("pdf")
    return modalities


def _capability_supported(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("supported") is True)


def _strip_models_prefix(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("models/"):
        return value[len("models/") :]
    return value


def _openai_supports_reasoning_effort(model_id: str) -> bool | None:
    if model_id.startswith(("gpt-5", "gpt-5.1", "gpt-5.2", "o1", "o3", "o4")):
        return True
    return None


def _xai_supports_reasoning_effort(model_id: str) -> bool | None:
    if model_id.startswith("grok-"):
        return True
    return None
