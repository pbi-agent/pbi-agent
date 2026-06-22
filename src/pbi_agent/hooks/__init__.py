"""Declarative command hooks for pbi-agent."""

from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.runtime import HookRuntime
from pbi_agent.hooks.schemas import HookEventName

__all__ = ["HookEventName", "HookRuntime", "discover_hooks"]
