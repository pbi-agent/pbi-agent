from __future__ import annotations

import json
from typing import Any

from pbi_agent.hooks.schemas import HookEventName, ParsedHookOutput


def parse_hook_output(
    *,
    event: HookEventName,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> ParsedHookOutput:
    if exit_code == 2:
        reason = stderr.strip() or stdout.strip()
        if event in {HookEventName.PRE_TOOL_USE, HookEventName.USER_PROMPT_SUBMIT}:
            return ParsedHookOutput(
                continue_=False,
                block_reason=reason or "Blocked by hook.",
            )
        if event == HookEventName.POST_TOOL_USE:
            return ParsedHookOutput(replacement=reason or "Hook provided feedback.")
        if event in {HookEventName.STOP, HookEventName.SUBAGENT_STOP}:
            return ParsedHookOutput(
                continuation_prompt=reason or "Continue after hook request."
            )

    parsed = _parse_json_object(stdout)
    if parsed is None:
        text = stdout.strip()
        return ParsedHookOutput(additional_context=text or None)

    if parsed.get("decision") == "block":
        return ParsedHookOutput(
            continue_=False,
            block_reason=str(parsed.get("reason") or "Blocked by hook."),
        )

    specific = parsed.get("hookSpecificOutput")
    if not isinstance(specific, dict):
        specific = {}
    system_message = _str_or_none(parsed.get("systemMessage"))
    common_context = system_message or _str_or_none(parsed.get("additionalContext"))
    continue_ = bool(parsed.get("continue", True))
    base = {
        "continue_": continue_,
        "stop_reason": _str_or_none(parsed.get("stopReason")),
        "system_message": system_message,
        "suppress_output": bool(parsed.get("suppressOutput", False)),
        "additional_context": common_context,
    }
    if not continue_:
        base["block_reason"] = (
            _str_or_none(parsed.get("stopReason"))
            or _str_or_none(parsed.get("reason"))
            or "Stopped by hook."
        )

    specific_event = specific.get("hookEventName")
    if specific_event is not None and specific_event != event.value:
        return ParsedHookOutput(**base)

    if event == HookEventName.PRE_TOOL_USE:
        decision = specific.get("permissionDecision")
        if decision == "deny":
            deny_base = dict(base)
            deny_base["continue_"] = False
            deny_base["block_reason"] = (
                _str_or_none(specific.get("permissionDecisionReason"))
                or "Blocked by hook."
            )
            return ParsedHookOutput(
                **deny_base,
            )
        updated_input = specific.get("updatedInput")
        if isinstance(updated_input, dict):
            return ParsedHookOutput(**base, updated_input=updated_input)
    if event == HookEventName.POST_TOOL_USE:
        replacement = (
            _str_or_none(specific.get("feedback"))
            or _str_or_none(specific.get("replacement"))
            or _str_or_none(specific.get("updatedOutput"))
        )
        context = (
            _str_or_none(specific.get("additionalContext"))
            or _str_or_none(specific.get("systemMessage"))
            or common_context
        )
        post_base = dict(base)
        post_base["additional_context"] = context
        return ParsedHookOutput(**post_base, replacement=replacement)
    if event in {HookEventName.STOP, HookEventName.SUBAGENT_STOP}:
        continuation = _str_or_none(specific.get("continuationPrompt")) or _str_or_none(
            parsed.get("continuationPrompt")
        )
        return ParsedHookOutput(**base, continuation_prompt=continuation)
    return ParsedHookOutput(**base)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
