"""Reusable provider endpoint resolution helpers."""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Mapping
from typing import Literal

from pbi_agent.config import DEFAULT_RESPONSES_URL, Settings
from pbi_agent.providers.azure import (
    AzureEndpointKind,
    azure_chat_completions_url,
    azure_endpoint_kind,
)

GoogleGcpEndpointShape = Literal[
    "gemini_generate_content",
    "openai_chat_completions",
    "openai_responses",
    "anthropic_messages",
]

_GOOGLE_GCP_OPENAPI_PREFIX = "/endpoints/openapi"
_GOOGLE_GCP_API_VERSION = "v1"
_GOOGLE_GCP_EXPRESS_API_VERSION = "v1beta1"


def chat_completions_url(settings: Settings) -> str:
    """Return an OpenAI-compatible Chat Completions endpoint."""
    if settings.provider == "azure":
        return azure_chat_completions_url(settings.responses_url)
    return settings.generic_api_url


def anthropic_messages_url(settings: Settings, *, default_url: str) -> str:
    """Return an Anthropic Messages endpoint."""
    if (
        settings.provider == "azure"
        and azure_endpoint_kind(settings.responses_url)
        == AzureEndpointKind.ANTHROPIC_MESSAGES
    ):
        return settings.responses_url
    return default_url


def responses_url(settings: Settings) -> str:
    """Return the configured Responses-style endpoint."""
    return settings.responses_url


def google_gcp_project_id(
    settings: Settings | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the configured Google Cloud project ID, if any."""
    if settings is not None and settings.google_cloud_project.strip():
        return settings.google_cloud_project.strip()
    source = os.environ if env is None else env
    return (
        source.get("PBI_AGENT_GOOGLE_CLOUD_PROJECT", "").strip()
        or source.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or source.get("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    )


def google_gcp_location(
    settings: Settings | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the configured Google Cloud location, defaulting to ``global``."""
    if settings is not None and settings.google_cloud_location.strip():
        return settings.google_cloud_location.strip()
    source = os.environ if env is None else env
    return (
        source.get("PBI_AGENT_GOOGLE_CLOUD_LOCATION", "").strip()
        or source.get("PBI_AGENT_GOOGLE_CLOUD_REGION", "").strip()
        or source.get("GOOGLE_CLOUD_LOCATION", "").strip()
        or source.get("GOOGLE_CLOUD_REGION", "").strip()
        or "global"
    )


def google_gcp_api_base_url(location: str) -> str:
    """Return the Vertex AI API host for a Google Cloud location."""
    normalized_location = location.strip() or "global"
    if normalized_location == "global":
        return "https://aiplatform.googleapis.com"
    return f"https://{normalized_location}-aiplatform.googleapis.com"


def google_gcp_endpoint_url(
    settings: Settings,
    shape: GoogleGcpEndpointShape,
    *,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
    require_project: bool = True,
) -> str:
    """Return the Google Cloud Vertex endpoint URL for a provider shape."""
    selected_model = model or settings.model
    base_url = _configured_google_gcp_url(settings)
    if base_url:
        if _google_gcp_url_is_exact_endpoint(base_url, shape):
            return base_url
        return _google_gcp_url_from_base(
            base_url,
            shape,
            selected_model,
            settings=settings,
            env=env,
            require_project=require_project,
        )

    project_id = google_gcp_project_id(settings, env=env)
    location = google_gcp_location(settings, env=env)
    if not project_id:
        if require_project:
            raise ValueError(
                "Missing Google Cloud project. Configure Google Cloud project "
                "in provider settings, pass --google-cloud-project, set "
                "PBI_AGENT_GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_PROJECT, or "
                "GOOGLE_CLOUD_PROJECT_ID, or configure --responses-url with a "
                "full Google Cloud Vertex endpoint."
            )
        return ""
    root_url = google_gcp_api_base_url(location)
    base_path = _google_gcp_project_location_path(project_id, location)
    return _google_gcp_endpoint_from_project_location(
        root_url,
        base_path,
        shape,
        selected_model,
    )


def google_gcp_express_endpoint_url(
    settings: Settings,
    shape: GoogleGcpEndpointShape,
    *,
    model: str | None = None,
) -> str:
    """Return a Google Cloud Vertex express-mode endpoint URL."""
    selected_model = model or settings.model
    base_url = _configured_google_gcp_url(settings)
    if base_url:
        if _google_gcp_url_is_exact_endpoint(base_url, shape):
            return base_url
        parsed = urllib.parse.urlparse(base_url)
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            path = f"/{_GOOGLE_GCP_EXPRESS_API_VERSION}"
        return _url_with_path(
            parsed,
            _append_path(path, _shape_suffix(shape, selected_model)),
        )

    return _url_with_path(
        urllib.parse.urlparse("https://aiplatform.googleapis.com"),
        f"/{_GOOGLE_GCP_EXPRESS_API_VERSION}/{_shape_suffix(shape, selected_model)}",
    )


def _configured_google_gcp_url(settings: Settings) -> str:
    configured_url = settings.responses_url.strip().rstrip("/")
    if not configured_url or configured_url == DEFAULT_RESPONSES_URL:
        return ""
    return configured_url


def _google_gcp_url_is_exact_endpoint(
    url: str,
    shape: GoogleGcpEndpointShape,
) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if shape == "gemini_generate_content":
        return path.endswith(":generateContent")
    if shape == "anthropic_messages":
        return path.endswith(":rawPredict") or path.endswith(":streamRawPredict")
    if shape == "openai_chat_completions":
        return path.endswith(f"{_GOOGLE_GCP_OPENAPI_PREFIX}/chat/completions")
    return path.endswith(f"{_GOOGLE_GCP_OPENAPI_PREFIX}/responses")


def _google_gcp_url_from_base(
    base_url: str,
    shape: GoogleGcpEndpointShape,
    model: str,
    *,
    settings: Settings,
    env: Mapping[str, str] | None,
    require_project: bool,
) -> str:
    parsed = urllib.parse.urlparse(base_url)
    path = parsed.path.rstrip("/")
    if shape in {"openai_chat_completions", "openai_responses"}:
        if path.endswith(_GOOGLE_GCP_OPENAPI_PREFIX):
            suffix = (
                "chat/completions"
                if shape == "openai_chat_completions"
                else "responses"
            )
            return _url_with_path(parsed, f"{path}/{suffix}")
        if path.endswith("/chat/completions") or path.endswith("/responses"):
            return base_url

    if _is_project_location_base_path(path):
        return _url_with_path(
            parsed,
            _shape_path_from_project_location(path, shape, model),
        )

    if not path or path in {"/", f"/{_GOOGLE_GCP_API_VERSION}"}:
        project_id = google_gcp_project_id(settings, env=env)
        location = google_gcp_location(settings, env=env)
        if not project_id:
            if not require_project:
                return ""
            raise ValueError(
                "Google Cloud Vertex base URL requires provider Google Cloud "
                "project, --google-cloud-project, PBI_AGENT_GOOGLE_CLOUD_PROJECT, "
                "GOOGLE_CLOUD_PROJECT, or GOOGLE_CLOUD_PROJECT_ID to derive the "
                "endpoint path."
            )
        return _google_gcp_endpoint_from_project_location(
            base_url,
            _google_gcp_project_location_path(project_id, location),
            shape,
            model,
        )

    return _url_with_path(parsed, _append_path(path, _shape_suffix(shape, model)))


def _google_gcp_endpoint_from_project_location(
    root_url: str,
    project_location_path: str,
    shape: GoogleGcpEndpointShape,
    model: str,
) -> str:
    parsed = urllib.parse.urlparse(root_url)
    return _url_with_path(
        parsed,
        _shape_path_from_project_location(project_location_path, shape, model),
    )


def _google_gcp_project_location_path(project_id: str, location: str) -> str:
    project = urllib.parse.quote(project_id, safe="-_.")
    selected_location = urllib.parse.quote(location or "global", safe="-_.")
    return (
        f"/{_GOOGLE_GCP_API_VERSION}/projects/{project}/locations/{selected_location}"
    )


def _shape_path_from_project_location(
    project_location_path: str,
    shape: GoogleGcpEndpointShape,
    model: str,
) -> str:
    return _append_path(project_location_path, _shape_suffix(shape, model))


def _shape_suffix(shape: GoogleGcpEndpointShape, model: str) -> str:
    if shape == "gemini_generate_content":
        model_id = urllib.parse.quote(_strip_model_prefix(model, "google"), safe="@.-_")
        return f"publishers/google/models/{model_id}:generateContent"
    if shape == "anthropic_messages":
        model_id = urllib.parse.quote(model, safe="@.-_")
        return f"publishers/anthropic/models/{model_id}:rawPredict"
    if shape == "openai_chat_completions":
        return "endpoints/openapi/chat/completions"
    return "endpoints/openapi/responses"


def _strip_model_prefix(model: str, prefix: str) -> str:
    return model.removeprefix(f"{prefix}/")


def _is_project_location_base_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 5:
        return False
    return (
        parts[0] == _GOOGLE_GCP_API_VERSION
        and parts[1] == "projects"
        and parts[3] == "locations"
        and len(parts) == 5
    )


def _append_path(base_path: str, suffix: str) -> str:
    path = base_path.rstrip("/")
    return f"{path}/{suffix.lstrip('/')}"


def _url_with_path(parsed: urllib.parse.ParseResult, path: str) -> str:
    return urllib.parse.urlunparse(parsed._replace(path=path))
