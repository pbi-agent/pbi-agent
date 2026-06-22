# Hooks

pbi-agent supports Codex-style declarative command hooks. Hooks are external
commands that receive lifecycle JSON on stdin and may add context, block work,
rewrite tool input, replace model-visible tool output, or request one guarded
continuation pass.

## Configuration

Hooks are loaded from JSON only:

```text
~/.pbi-agent/hooks.json
<workspace>/.agents/hooks.json
```

Example:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "shell|apply_patch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .agents/hooks/check_policy.py",
            "timeout": 30,
            "statusMessage": "Checking policy"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .agents/hooks/session_end.py"
          }
        ]
      }
    ]
  }
}
```

Only `type: "command"` runs today. Unsupported `prompt`, `agent`, and
`async: true` handlers are parsed as diagnostics and skipped.

## Trust review

Hooks are skipped until trusted unless they come from a trusted managed source.
pbi-agent stores trust state in
`~/.pbi-agent/hooks_state.json` using a stable hook identity plus a normalized
hash of the hook definition. Formatting changes to JSON do not invalidate trust,
but command, matcher, timeout, status message, or managed-policy changes do.

Review hooks with either:

```bash
pbi-agent hooks
pbi-agent hooks trust '<hook-key>'
pbi-agent hooks disable '<hook-key>'
pbi-agent hooks enable '<hook-key>'
```

or open **Settings → Hooks** in the web UI. The browser shows event, matcher,
command/source, status message, timeout, trust status, current hash, enabled
state, managed state, and diagnostics.

The web API mirrors the UI:

```text
GET  /api/hooks
POST /api/hooks/trust
POST /api/hooks/disable
POST /api/hooks/enable
```

Startup warnings appear in CLI stderr and in the web app when untrusted or
modified hooks are discovered. Those hooks remain skipped.

## Managed hooks

Managed hooks are reserved for trusted policy sources. Ordinary global
`~/.pbi-agent/hooks.json` and project `.agents/hooks.json` files cannot make a
hook trusted-by-policy by setting `"managed": true`; that self-declaration is
ignored and reported as a diagnostic.

A future trusted managed source may mark a handler as trusted-by-policy:

```json
{
  "type": "command",
  "command": "python3 .agents/hooks/required_policy.py",
  "managed": true
}
```

Managed hooks from trusted policy sources run without user trust state and
cannot be disabled through the normal CLI/API/UI controls. Use this sparingly for
controlled environments; it is not a plugin sandbox.

## Dangerous trust bypass

Automation can explicitly bypass hook trust review:

```bash
pbi-agent --dangerously-bypass-hook-trust run --prompt "..."
PBI_AGENT_DANGEROUSLY_BYPASS_HOOK_TRUST=1 pbi-agent run --prompt "..."
```

This makes untrusted and modified hooks runnable for that process and emits a
warning. Explicitly disabled hooks remain disabled. It does not edit
`hooks_state.json`.

## Matchers

Matchers use the Codex-style rules:

- omitted, empty, or `*`: match all
- `foo|bar`: exact alternatives
- otherwise: regular expression

Matcher input by event:

| Event | Matcher input |
| --- | --- |
| `SessionStart` | `startup`, `resume`, `clear`, or `compact` |
| `UserPromptSubmit` | ignored |
| `PreToolUse` / `PostToolUse` | tool name |
| `PreCompact` / `PostCompact` | `manual` or `auto` |
| `Stop` | ignored |
| `SubagentStart` / `SubagentStop` | sub-agent type/name |

## Hook input

Commands run in the session workspace. pbi-agent writes one JSON object to stdin
with common fields:

```json
{
  "session_id": "string-or-null",
  "turn_id": "string-or-null",
  "cwd": "/workspace",
  "hook_event_name": "PreToolUse",
  "model": "gpt-5.4",
  "provider": "openai",
  "workspace_directory_key": "string-or-null",
  "agent_name": "main",
  "agent_type": "session_turn",
  "transcript_path": null
}
```

Event-specific fields include `prompt`, `tool_name`, `tool_input`,
`tool_response`, compaction reason, sub-agent instruction, and final response
text where relevant.

## Hook output

Hooks can print JSON to stdout:

```json
{
  "continue": true,
  "systemMessage": "Extra context for the model",
  "suppressOutput": false
}
```

`PreToolUse` can deny or rewrite input:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Blocked by policy."
  }
}
```

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": { "command": "echo rewritten" }
  }
}
```

`PostToolUse` can replace the model-visible tool result:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "replacement": "Use this feedback instead of the raw tool output."
  }
}
```

`Stop` and `SubagentStop` can request one continuation prompt:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "continuationPrompt": "Run one final verification pass."
  }
}
```

Exit code `2` is also event-aware: it blocks `PreToolUse` and
`UserPromptSubmit`, replaces `PostToolUse` output with stderr feedback, and
requests a continuation for `Stop` / `SubagentStop`.

## Limitations

- Hook subprocesses are not a security sandbox.
- Only command hooks execute today.
- `PermissionRequest` hooks are deferred until pbi-agent has a first-class
  permission/approval path.
- `SubagentStop` continuation is intentionally one additional child pass only,
  so hooks cannot loop forever.