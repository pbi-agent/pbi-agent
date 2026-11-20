# pbi-agent hooks disable

Disable a discovered hook so pbi-agent never runs it, without editing the hook config.

## Purpose
Sets `enabled: false` for the hook key in `~/.pbi-agent/hooks_state.json`; the hook's
status becomes `disabled` and it is skipped. Use it to silence a noisy or broken hook
while keeping it in `.agents/hooks.json` (which may be shared with a team). A disabled
hook stays disabled even with `--dangerously-bypass-hook-trust`. To remove a hook for
everyone, edit the hooks JSON file instead.

## Usage
```text
pbi-agent hooks disable [--project-dir PROJECT_DIR] hook_key
```

## Options and arguments
- `hook_key` (positional, required): the exact `key:` value shown by `pbi-agent hooks`
  (or `key` in `pbi-agent hooks --json`).
- `--project-dir PROJECT_DIR`: workspace whose `.agents/hooks.json` is searched for
  the key (default: current directory). Global hooks are always searched.

## Examples
```bash
# Disable a global PostToolUse hook
pbi-agent hooks disable 'global:/home/me/.pbi-agent/hooks.json:PostToolUse:apply_patch:sha256:5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c:1'
# Disable a project hook of another workspace
pbi-agent hooks disable 'project:/home/me/repo/.agents/hooks.json:PreToolUse:shell:sha256:7893bccfcc700b3f4c3c24d6c0f7bec41c8fdbf1aac6cf76ee92a092bfa6edc4:1' --project-dir /home/me/repo
```

## Workflows
1. Silence a failing hook: `pbi-agent hooks` to find its key,
   `pbi-agent hooks disable 'KEY'`, confirm `[disabled]` in `pbi-agent hooks`.
2. Bring it back later with `pbi-agent hooks enable 'KEY'` (or
   `pbi-agent hooks trust 'KEY'`, which also re-enables it).

## Related commands
- `pbi-agent hooks`: list hooks, keys, and statuses.
- `pbi-agent hooks enable`: the inverse action.
- `pbi-agent web`: Settings -> Hooks can also disable hooks.

## Pitfalls
- Prints `Disabled hook: <event> <command>` and exits 0 on success.
- Unknown key: `Error: hook not found: KEY` on stderr, exit 1. Project keys embed the
  config file's absolute path, so run from (or pass `--project-dir` for) that workspace.
- Managed hooks cannot be toggled: `Error: managed hooks cannot be disabled or enabled
  manually.` on stderr, exit 2.
- Changing the hook's command changes its key; re-check `pbi-agent hooks` after edits.
- Put `--project-dir` after `disable`; before the action it is ignored.
