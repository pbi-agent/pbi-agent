from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from pbi_agent.auth.models import AUTH_MODE_API_KEY
from pbi_agent.config import (
    ConfigError,
    PROVIDER_API_KEY_ENVS,
    ProviderConfig,
    load_internal_config,
    provider_supports_stt,
    slugify,
)
from pbi_agent.stt.audio import convert_wav_to_wav_s16le_16k_mono, validate_wav_bytes
from pbi_agent.stt.base import (
    ResolvedSttProvider,
    SttConfigurationError,
)
from pbi_agent.stt.registry import get_stt_backend


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    validate_wav_bytes(wav_bytes)
    with tempfile.TemporaryDirectory(prefix="pbi-agent-stt-") as tmp_dir:
        wav_path = Path(tmp_dir) / "original.wav"
        wav_path.write_bytes(wav_bytes)
        return transcribe_wav_file(wav_path)


def transcribe_wav_file(wav_path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="pbi-agent-stt-prepared-") as tmp_dir:
        prepared_wav_path = Path(tmp_dir) / "upload.wav"
        convert_wav_to_wav_s16le_16k_mono(wav_path, prepared_wav_path)
        provider = resolve_selected_stt_provider()
        backend = get_stt_backend(provider.kind)
        return backend.transcribe(prepared_wav_path, provider).strip()


def resolve_selected_stt_provider() -> ResolvedSttProvider:
    load_dotenv()
    config = load_internal_config()
    provider_id = config.web.stt_provider_id
    if not provider_id:
        raise SttConfigurationError(
            "No speech-to-text provider configured. Select an STT provider in settings."
        )

    providers = {provider.id: provider for provider in config.providers}
    try:
        normalized_provider_id = slugify(provider_id)
    except ConfigError as exc:
        raise SttConfigurationError(
            f"Selected speech-to-text provider '{provider_id}' is invalid."
        ) from exc
    provider = providers.get(normalized_provider_id)
    if provider is None:
        raise SttConfigurationError(
            f"Selected speech-to-text provider '{provider_id}' was not found."
        )
    if not provider_supports_stt(provider.kind):
        raise SttConfigurationError(
            f"Selected provider '{provider.id}' does not support speech-to-text."
        )

    api_key = _resolve_stt_api_key(provider)
    if not api_key:
        env_hint = _api_key_env_hint(provider)
        hint = f" Set {env_hint} or configure a provider API key." if env_hint else ""
        raise SttConfigurationError(
            f"Missing API key for speech-to-text provider '{provider.id}'.{hint}"
        )
    return ResolvedSttProvider(
        provider_id=provider.id,
        kind=provider.kind,
        api_key=api_key,
    )


def _resolve_stt_api_key(provider: ProviderConfig) -> str:
    if provider.auth_mode != AUTH_MODE_API_KEY:
        return ""
    if provider.api_key_env is not None:
        return os.getenv(provider.api_key_env, "").strip()
    if provider.api_key.strip():
        return provider.api_key.strip()
    for env_name in _default_api_key_env_names(provider.kind):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def _api_key_env_hint(provider: ProviderConfig) -> str | None:
    if provider.api_key_env:
        return provider.api_key_env
    env_names = _default_api_key_env_names(provider.kind)
    return env_names[0] if env_names else None


def _default_api_key_env_names(provider_kind: str) -> tuple[str, ...]:
    env_names: list[str] = []
    provider_env = PROVIDER_API_KEY_ENVS.get(provider_kind)
    if provider_env:
        env_names.append(provider_env)
    if provider_kind == "openai":
        env_names.append("PBI_AGENT_API_KEY")
    return tuple(dict.fromkeys(env_names))
