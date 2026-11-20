# pbi-agent hooks

List discovered command hooks with their trust status, and trust, enable, or disable them.

## Purpose
Command hooks are external commands that pbi-agent runs on lifecycle events
(`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`,
`PostCompact`, `Stop`, `SubagentStart`, `SubagentStop`). They are loaded from
`~/.pbi-agent/hooks.json` (source `global`) and `<workspace>/.agents/hooks.json`
(source `project`). A hook only runs when its status is `trusted` (or `managed`);
`untrusted`, `modified`, and `disabled` hooks are skipped. Trust state lives in
`~/.pbi-agent/hooks_state.json`, keyed by hook key plus a hash of the definition.

With no action, `pbi-agent hooks` lists every discovered hook: a header line
`<event> [<status>] matcher=<matcher or *> source=<source>`, then `command:`, `key:`,
`hash:`, optional `status:`, `timeout:` (default 600s), and per-hook diagnostics.
Config parse problems go to stderr under `Diagnostics:`. The Settings -> Hooks page of
`pbi-agent web` offers the same review.

## Usage
```text
pbi-agent hooks [--project-dir PROJECT_DIR] [--json]
pbi-agent hooks <action> [--project-dir PROJECT_DIR] hook_key
```

## Subcommands
When no action is given, the hooks are listed (exit 0, also when none are found:
`No hooks discovered.`).
- `pbi-agent hooks trust`: trust a hook's current definition so it runs. Guide: `pbi-agent hooks trust --doc`.
- `pbi-agent hooks enable`: re-enable a disabled hook. Guide: `pbi-agent hooks enable --doc`.
- `pbi-agent hooks disable`: disable a hook so it never runs. Guide: `pbi-agent hooks disable --doc`.

## Options and arguments
These belong to the listing (no action):
- `--project-dir PROJECT_DIR`: workspace whose `.agents/hooks.json` is read
  (default: current directory). Global hooks are always included.
- `--json`: print `{"hooks": [...], "diagnostics": [...]}` instead of text. Each hook
  has `key`, `event`, `matcher`, `command`, `source`, `source_path`,
  `status_message`, `timeout`, `trust_status`, `current_hash`, `enabled`, `managed`,
  `diagnostics`, and `runnable`.

## Examples
```bash
# List hooks for the current workspace
pbi-agent hooks
# Machine-readable listing for another workspace
pbi-agent hooks --project-dir ../other-repo --json
# Keys of hooks that will be skipped (needs jq)
pbi-agent hooks --json | jq -r '.hooks[] | select(.runnable | not) | .key'
```

## Workflows
1. Review new hooks: run `pbi-agent hooks`, read each `command:` and the script it
   calls, then `pbi-agent hooks trust 'KEY'` for the ones you accept.
2. After editing `.agents/hooks.json`: changed hooks show `[modified]` and stop
   running; run `pbi-agent hooks` again and trust its current key.
3. Temporarily silence a hook: `pbi-agent hooks disable 'KEY'`, later
   `pbi-agent hooks enable 'KEY'`.

## Related commands
- `pbi-agent web`: Settings -> Hooks shows and changes the same state.
- `pbi-agent --dangerously-bypass-hook-trust run -p "..."`: run untrusted/modified
  hooks for one process (disabled hooks stay disabled).

## Pitfalls
- `--json` only affects the listing; `trust`/`enable`/`disable` always print text.
- Parent `--project-dir` placed before an action is ignored (the action resets it to
  `.`). Put it after the action: `pbi-agent hooks trust KEY --project-dir DIR`.
- Keys contain colons and absolute paths; quote them in the shell.
- `pbi-agent run` and `pbi-agent web` print a stderr warning when hooks need review.
- Only `type: "command"` hooks without `async: true` are listed; others become diagnostics.
