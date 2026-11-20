# pbi-agent hooks enable

Re-enable a hook that was disabled with `pbi-agent hooks disable`.

## Purpose
Sets `enabled: true` for the hook key in `~/.pbi-agent/hooks_state.json`. The hook's
status then falls back to its trust state: `trusted` if it was trusted before and its
definition is unchanged, otherwise `modified` (skipped until trusted). `enable` does
not trust anything; use `pbi-agent hooks trust` to approve a hook's current definition.

## Usage
```text
pbi-agent hooks enable [--project-dir PROJECT_DIR] hook_key
```

## Options and arguments
- `hook_key` (positional, required): the exact `key:` value shown by `pbi-agent hooks`
  (or `key` in `pbi-agent hooks --json`).
- `--project-dir PROJECT_DIR`: workspace whose `.agents/hooks.json` is searched for
  the key (default: current directory). Global hooks are always searched.

## Examples
```bash
# Re-enable a previously disabled project hook
pbi-agent hooks enable 'project:/home/me/repo/.agents/hooks.json:Stop::sha256:2b1f0c9d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c:1'
# Same, for a workspace other than the cwd
pbi-agent hooks enable 'project:/home/me/repo/.agents/hooks.json:Stop::sha256:2b1f0c9d8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c:1' --project-dir /home/me/repo
```

## Workflows
1. Undo a temporary disable: `pbi-agent hooks disable 'KEY'`, do the work, then
   `pbi-agent hooks enable 'KEY'` and check `pbi-agent hooks` shows `[trusted]`.
2. If the hook shows `[modified]` after enabling, review the command and run
   `pbi-agent hooks trust 'KEY'`.

## Related commands
- `pbi-agent hooks`: list hooks, keys, and statuses.
- `pbi-agent hooks disable`: the inverse action.
- `pbi-agent hooks trust`: trust a definition (also enables it).

## Pitfalls
- Prints `Enabled hook: <event> <command>` and exits 0 on success.
- Unknown key: `Error: hook not found: KEY` on stderr, exit 1. Project keys embed the
  config file's absolute path, so run from (or pass `--project-dir` for) that workspace.
- Managed hooks cannot be toggled: `Error: managed hooks cannot be disabled or enabled
  manually.` on stderr, exit 2.
- Enabling a never-trusted hook does not make it run; it shows `[modified]`.
- Put `--project-dir` after `enable`; before the action it is ignored.
