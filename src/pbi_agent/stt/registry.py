from __future__ import annotations

from importlib import import_module

from pbi_agent.stt.base import SttBackend, SttConfigurationError

_DEFAULT_BACKEND_MODULES = (
    "pbi_agent.stt.openai",
    "pbi_agent.stt.deepgram",
    "pbi_agent.stt.elevenlabs",
)
_BACKENDS: dict[str, SttBackend] = {}
_DEFAULTS_LOADED = False


def register_stt_backend(backend: SttBackend) -> None:
    _BACKENDS[backend.kind] = backend


def get_stt_backend(provider_kind: str) -> SttBackend:
    _ensure_default_backends_loaded()
    backend = _BACKENDS.get(provider_kind)
    if backend is None:
        raise SttConfigurationError(
            f"Provider kind '{provider_kind}' does not support speech-to-text."
        )
    return backend


def list_stt_backend_kinds() -> tuple[str, ...]:
    _ensure_default_backends_loaded()
    return tuple(sorted(_BACKENDS))


def _ensure_default_backends_loaded() -> None:
    global _DEFAULTS_LOADED
    if _DEFAULTS_LOADED:
        return
    _DEFAULTS_LOADED = True
    for module_name in _DEFAULT_BACKEND_MODULES:
        import_module(module_name)
