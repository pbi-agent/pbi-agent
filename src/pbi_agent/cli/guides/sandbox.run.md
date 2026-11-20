# pbi-agent sandbox run

Run one prompt turn of the agent inside the Docker sandbox and exit with its result.

## Purpose
Use `sandbox run` for scripted one-shot work whose shell commands and file edits must execute in a container. The host CLI starts `docker run` with the current directory mounted, and the container runs `pbi-agent run` with the options below. Provider settings come from global flags (forwarded as `PBI_AGENT_*` env vars), forwarded host env vars, `--env-file`, and the saved config in the shared `~/.pbi-agent`. Use host `pbi-agent run` when no isolation is needed or you need `--allowed-tools`. Sandbox options (`--image`, `--env-file`, `--rebuild`, `--local-source`, `--read-only-repo`, `-d`) are described in `pbi-agent sandbox --doc`.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] sandbox [SANDBOX OPTIONS] run -p PROMPT [--image IMAGES] [--project-dir PROJECT_DIR] [--session-id SESSION_ID] [--include-tool-history] [--show-steps]
```

## Options and arguments
- `-p, --prompt PROMPT` (required): the user prompt.
- `--image IMAGES`: attach a workspace image to the prompt; repeatable. Paths are resolved inside the project directory in the container. Not the same as `sandbox --image`.
- `--project-dir PROJECT_DIR`: directory relative to the current directory to scope the run to. Default `.`. The whole current directory is still mounted; sessions are keyed by the host path of this directory.
- `--session-id SESSION_ID`: forwarded to the inner `run` to resume a saved session.
- `--include-tool-history`: with `--session-id`, replay prior tool calls and results into the model context.
- `--show-steps`: print all intermediate steps instead of only the final response.

## Examples
```bash
# One prompt in the sandbox
pbi-agent sandbox run -p "Summarize this repository."

# Inspection only: the repository is mounted read-only
pbi-agent sandbox --read-only-repo run -p "Review this repo without editing files."

# Scope to a package and attach an image
pbi-agent sandbox run --project-dir packages/api --image docs/flow.png -p "Explain this diagram against the code."

# Pick a model and show every step
pbi-agent --model gpt-5.4 sandbox run --show-steps -p "Run the tests and fix the first failure."
```

## Workflows
1. Isolated fix: `pbi-agent sandbox run -p "..."`, then review the result on the host with `git diff` (the mount is writable by default).
2. CI-style check: `pbi-agent sandbox --env-file .env.sandbox run -p "..."` and use the exit code (the inner `run` code: 0 ok, 4 tool errors, 1 runtime error, 2 config error).
3. Follow up interactively: read `session_id=<id>` from the output, then open the session in `pbi-agent web` or `pbi-agent sandbox web`.

## Related commands
- `pbi-agent sandbox`: parent command; image, env file, mounts and detach options.
- `pbi-agent run`: the same turn on the host, with `--allowed-tools`.
- `pbi-agent sessions`: list saved sessions, including sandbox ones, under the host path.

## Pitfalls
- There is no `--allowed-tools` here and it cannot be passed as a global option; tool groups come from the selected profile. Use host `pbi-agent run --allowed-tools ...` to restrict tools per run.
- Sandbox options go before `run`: `pbi-agent sandbox --rebuild run -p "..."`; after `run` they are a usage error (exit 2).
- With `-d`, Docker prints only the container ID and the output is not streamed; the container is removed when it exits.
- Resuming with `--session-id` makes the inner `run` switch to the session's recorded host directory, which is not mounted at that path in the container. If it fails with `Project directory does not exist`, resume with host `pbi-agent run --session-id` instead.
- Docker missing or not running exits 1; a failed image build returns the `docker build` exit code.
