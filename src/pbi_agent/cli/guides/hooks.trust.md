# pbi-agent hooks trust

Trust the current definition of a discovered hook so pbi-agent runs it.

## Purpose
Hooks from `~/.pbi-agent/hooks.json` and `<workspace>/.agents/hooks.json` are skipped
until trusted. `trust` records the hook's current hash in
`~/.pbi-agent/hooks_state.json` and marks it enabled, so its status becomes `trusted`.
If the hook's command, matcher, timeout, or status message changes later, it turns
`modified` and is skipped until trusted again. Inspect the command before trusting:
hooks run as normal subprocesses, not in a sandbox.

## Usage
```text
pbi-agent hooks trust [--project-dir PROJECT_DIR] hook_key
```

## Options and arguments
- `hook_key` (positional, required): the exact `key:` value shown by `pbi-agent hooks`
  (or `key` in `pbi-agent hooks --json`).
- `--project-dir PROJECT_DIR`: workspace whose `.agents/hooks.json` is searched for
  the key (default: current directory). Global hooks are always searched.

## Examples
```bash
# Trust a project hook (copy the key from `pbi-agent hooks`)
pbi-agent hooks trust 'project:/home/me/repo/.agents/hooks.json:PreToolUse:shell:sha256:7893bccfcc700b3f4c3c24d6c0f7bec41c8fdbf1aac6cf76ee92a092bfa6edc4:1'
# Trust the first listed hook of another workspace (needs jq)
pbi-agent hooks trust "$(pbi-agent hooks --project-dir ../repo --json | jq -r '.hooks[0].key')" --project-dir ../repo
```

## Workflows
1. Review and accept: `pbi-agent hooks`, read the `command:` and its script, then
   `pbi-agent hooks trust 'KEY'`; confirm the header now shows `[trusted]`.
2. Re-trust after an edit: the hook shows `[modified]`; run `pbi-agent hooks` to get
   its current key and trust it again.

## Related commands
- `pbi-agent hooks`: list hooks, keys, and statuses.
- `pbi-agent hooks disable`: stop a hook from running without removing it.
- `pbi-agent hooks enable`: undo a disable.

## Pitfalls
- Prints `Trusted hook: <event> <command>` and exits 0 on success.
- Unknown key: `Error: hook not found: KEY` on stderr, exit 1. Keys embed the config
  file's absolute path, so a project key is only found when `--project-dir` (or the
  cwd) points at that workspace.
- Put `--project-dir` after `trust`; `pbi-agent hooks --project-dir DIR trust KEY`
  ignores DIR.
- Trusting a disabled hook also re-enables it.
- Managed hooks print `Managed hooks are trusted by policy; no action needed.` (exit 0).
