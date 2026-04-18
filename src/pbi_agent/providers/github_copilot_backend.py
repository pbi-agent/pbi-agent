from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL

GITHUB_COPILOT_MODELS_URL = "https://api.githubcopilot.com/models"
GITHUB_COPILOT_CHAT_COMPLETIONS_URL = "https://api.githubcopilot.com/chat/completions"

GitHubCopilotBackendMode = Literal["responses", "chat_completions"]

_OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")


@dataclass(frozen=True, slots=True)
class GitHubCopilotBackendDefinition:
    mode: GitHubCopilotBackendMode
    request_url: str


def github_copilot_backend_for_model(model: str) -> GitHubCopilotBackendDefinition:
    if is_github_copilot_openai_model(model):
        return GitHubCopilotBackendDefinition(
            mode="responses",
            request_url=GITHUB_COPILOT_RESPONSES_URL,
        )
    return GitHubCopilotBackendDefinition(
        mode="chat_completions",
        request_url=GITHUB_COPILOT_CHAT_COMPLETIONS_URL,
    )


def is_github_copilot_openai_model(model: str) -> bool:
    normalized = model.strip().lower()
    if not normalized:
        return True
    return normalized.startswith(_OPENAI_MODEL_PREFIXES)
