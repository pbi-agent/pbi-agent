# pbi-agent sandbox

Run the whole agent (web UI or one prompt turn) inside a Docker Desktop Linux container, with the current directory mounted as the workspace.

## Purpose
Use `sandbox` when model-requested shell commands, file edits, MCP servers and sub-agents should execute in a container instead of directly on the host. The current directory is bind-mounted at `/workspace/<id>` (writable unless `--read-only-repo`), host `~/.pbi-agent` is bind-mounted so config, profiles, sessions and Kanban tasks are shared with non-sandbox runs, and history is keyed by the real host path. The container runs as a non-root user with a read-only image filesystem, all capabilities dropped, `no-new-privileges`, 512 pids, 4 GB memory and a 256 MB `/tmp`. Requires the `docker` CLI and a running Docker Desktop.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] sandbox [--image IMAGE] [--env-file ENV_FILE] [--rebuild] [--local-source] [--read-only-repo] [-d] [<command> ...]
```

## Subcommands
- `pbi-agent sandbox web`: serve the browser UI from the container, published on the host. Guide: `pbi-agent sandbox web --doc`.
- `pbi-agent sandbox run`: run one prompt turn in the container. Guide: `pbi-agent sandbox run --doc`.

With no subcommand, `pbi-agent sandbox` runs `sandbox web` with its defaults (host `127.0.0.1`, port `7424`). Web options such as `--port` need the explicit `web` subcommand.

## Options and arguments
These belong to `sandbox` itself and must come before `web` or `run`.
- `--image IMAGE`: Docker image to run. Default `pbi-agent-sandbox:<installed version>`. If the image does not exist locally it is built from the Dockerfile bundled in the package, installing the matching pbi-agent version from PyPI. Use a custom image for extra system packages (runtime `apk add` is not possible).
- `--env-file ENV_FILE`: env file passed to `docker run --env-file` (path relative to the current directory), for provider keys and `PBI_AGENT_*` settings.
- `--rebuild`: rebuild the image before running, even if it exists. A failed build returns the `docker build` exit code.
- `--local-source`: before starting, `pip install -e` the mounted current directory inside the container. For developing pbi-agent itself from its checkout.
- `--read-only-repo`: mount the workspace read-only; file edits and writing commands fail.
- `-d, --detach`: run the container in the background. Docker prints the container ID; for `web` the CLI then waits for the server and opens the host browser before returning.

**Forwarded from the host.** All `PBI_AGENT_*` env vars, the provider key vars (`OPENAI_API_KEY`, `AZURE_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `GENERIC_API_KEY`), Google Cloud project/location/token vars and proxy vars. Global runtime flags (`--provider`, `--model`, `--profile-id`, `--api-key`, `--max-tokens`, ...) become the matching `PBI_AGENT_*` env vars, and `--verbose` is passed to the inner command. `--dangerously-bypass-hook-trust` is not forwarded. Existing `~/.gitconfig`, `~/.config/git`, `~/.git-credentials`, `~/.ssh` and `~/.config/gh` are mounted read-only.

## Examples
```bash
# Web UI in the sandbox (same as `pbi-agent sandbox web`)
pbi-agent sandbox

# Detached web UI on another port
pbi-agent sandbox -d web --port 9001

# One prompt with credentials from an env file and a read-only repo
pbi-agent sandbox --env-file .env.sandbox --read-only-repo run -p "Review this repo without editing files."

# Rebuild the image, then run with a specific profile
pbi-agent --profile-id fast sandbox --rebuild run -p "Run the test suite and summarize failures."
```

## Workflows
1. Safe review: `pbi-agent sandbox --read-only-repo run -p "..."`, then apply changes yourself on the host.
2. Background UI: `pbi-agent sandbox -d web`, work in the browser, then `docker stop <container-id>` (the container is removed on stop).
3. Test a pbi-agent checkout: from the repo root, `uv run pbi-agent sandbox --local-source web`; after dependency changes use `--rebuild`.

## Related commands
- `pbi-agent web`: the same UI on the host, without Docker.
- `pbi-agent run`: the same one-shot turn on the host; supports `--allowed-tools`.
- `pbi-agent sessions`: sandbox sessions appear here too, under the host path.

## Pitfalls
- Order matters: `pbi-agent [GLOBAL OPTIONS] sandbox [SANDBOX OPTIONS] web|run [COMMAND OPTIONS]`. `pbi-agent sandbox run --rebuild ...` is a usage error (exit 2).
- `sandbox --image` is the Docker image; `sandbox run --image` attaches a prompt image.
- Docker missing or not running exits 1 with an error. Otherwise the exit code is the container's (for `run`, the inner `pbi-agent run` code).
- The container is named `pbi-agent-<folder name>`, so only one sandbox per folder name can run at a time.
- Only the listed env vars are forwarded; pass anything else with `--env-file`.
- `--d` is ambiguous (`--detach` and `--doc`); use `-d` or `--detach`.
- A writable mount gives the agent full write access to the repository; Docker does not protect mounted files.
