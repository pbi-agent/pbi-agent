from __future__ import annotations

IMAGE_ENABLED_PROVIDERS = frozenset(
    {"openai", "azure", "chatgpt", "github_copilot", "anthropic", "google"}
)


def provider_supports_images(provider: str) -> bool:
    return provider.strip().lower() in IMAGE_ENABLED_PROVIDERS


def image_excluded_tools(provider: str) -> set[str]:
    if provider_supports_images(provider):
        return set()
    return {"read_image"}
