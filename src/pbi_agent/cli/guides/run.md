# pbi-agent run

Run one prompt turn of the agent in the terminal, print the final response, and exit.

## Purpose
Use `run` for scripted, non-interactive work: one prompt in, one answer out, saved as a normal session that the web UI and `pbi-agent sessions` can see. Use `pbi-agent web` for interactive multi-turn work, and `pbi-agent sandbox run` to run the same turn inside a Docker container. Unlike `web`, `run` resolves provider settings from global flags (`--provider`, `--model`, `--profile-id`, ...), `PBI_AGENT_*` env vars, `.env`, the selected saved profile (default: the active profile), then defaults.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] run -p PROMPT [--image IMAGES] [--project-dir PROJECT_DIR] [--session-id SESSION_ID] [--include-tool-history] [--show-steps] [--allowed-tools ALLOWED_TOOLS]
```

## Options and arguments
- `-p, --prompt PROMPT` (required): the user prompt. A prompt starting with `/name` activates the matching project command (see `pbi-agent commands`).
- `--image IMAGES`: attach a local image to the prompt; repeatable. Paths are resolved inside the project directory and must not escape it. Formats are detected from file content (PNG, JPEG, WEBP, HEIC, HEIF), max 20 MB each. Providers without image input (xAI, Generic) fail fast.
- `--project-dir PROJECT_DIR`: directory (relative to the current directory) the agent runs in and scopes tools to; the process changes into it for the turn. Default: `.`.
- `--session-id SESSION_ID`: resume a saved session. The run then uses that session's recorded directory instead of `--project-dir`.
- `--include-tool-history`: with `--session-id`, also replay prior tool calls and results into the model context (default: user and assistant messages only).
- `--show-steps`: print everything (welcome panel, thinking, tool calls, sub-agents, usage). Default: only the final response.
- `--allowed-tools ALLOWED_TOOLS`: comma-separated built-in tool groups to allow for this run: `read-image` (alias `read`), `write`, `web`, `sub-agent`, `shell`. Replaces the profile's tool visibility for this run; groups not listed are disabled.

## Examples
```bash
# One-shot question about the current repository
pbi-agent run -p "Summarize the main modules in this repository."

# Use a saved profile and print every step
pbi-agent --profile-id fast run --show-steps -p "List the failing tests."

# Attach an image
pbi-agent run -p "Read the text in this screenshot." --image docs/screenshot.png

# Resume a session with its tool history
pbi-agent run --session-id 3f2a9c1e --include-tool-history -p "Continue from the files you inspected."

# Read-only style run in a sub-package without shell or write tools
pbi-agent run --project-dir packages/api --allowed-tools read,web -p "Explain the request flow."
```

## Workflows
1. Chain turns from a script: run `pbi-agent run -p "..."`, read the last stdout line `session_id=<id>`, then call `pbi-agent run --session-id <id> -p "..."` for the next turn.
2. Find an older session to resume: `pbi-agent sessions` (or `--all-dirs`), copy its ID, then `pbi-agent run --session-id <id> --include-tool-history -p "..."`.
3. Pin the model for CI: `pbi-agent config profiles list` to find a profile ID, then `pbi-agent --profile-id <id> run -p "..."`; check the exit code (0 ok, 4 tool errors).

## Related commands
- `pbi-agent sessions`: list saved sessions and their IDs for `--session-id`.
- `pbi-agent web`: interactive browser UI over the same sessions.
- `pbi-agent sandbox run`: the same one-shot turn inside a Docker sandbox.
- `pbi-agent config profiles`: manage the saved profiles that `run` resolves.

## Pitfalls
- Global options go before `run`: `pbi-agent --model gpt-5.4 run -p "..."`. `pbi-agent run --model ...` is a usage error (exit 2).
- Exit codes: 0 success; 4 the turn finished but at least one tool call errored; 1 runtime/provider error, missing project directory, or unknown `--session-id`; 2 usage or configuration error (for example a missing API key or an unknown `--allowed-tools` group); 130 on Ctrl+C.
- Without `--show-steps`, stdout is just the final response followed by `session_id=<id>`; warnings (such as unreviewed hooks) go to stderr.
- Project hooks that are new or modified since review only produce a warning; use `pbi-agent hooks` to review them. The global `--dangerously-bypass-hook-trust` runs them without review.
- Session directories are stored lowercased. On a case-sensitive filesystem, `--session-id` for a workspace whose path has uppercase letters may fail with `Project directory does not exist`.
