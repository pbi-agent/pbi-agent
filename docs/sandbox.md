---
title: 'Docker Sandbox'
description: 'Run pbi-agent inside a Docker Desktop Linux container.'
---

# Docker Sandbox

`pbi-agent sandbox` runs the whole agent process inside a Docker Desktop Linux container. The current repository is mounted under a per-repository directory below `/workspace`, and the agent runs from that mounted repository directory, so model-requested shell commands, file reads, file edits, MCP servers, and sub-agents execute inside the container instead of directly on the host.

This is intended for Docker Desktop on Windows using Linux containers. Docker Desktop provides the VM-backed boundary; the host still sees normal Git diffs because the repository is bind-mounted.

## Requirements

- Docker Desktop installed and running.
- Linux containers enabled in Docker Desktop.
- `docker` available on your host `PATH`.
- Provider credentials available through environment variables, `.env`, saved pbi-agent config, or `--env-file`.

## Start The Web UI

From your repository root:

```bash
pbi-agent sandbox web
```

When installed from PyPI, `pbi-agent sandbox` builds a small sandbox image from the Dockerfile bundled inside the installed package. The CLI reads its installed package version and passes it as `PBI_AGENT_VERSION`, so the image installs the matching PyPI package version with:

```dockerfile
python -m pip install --prefer-binary "pbi-agent==${PBI_AGENT_VERSION}"
```

The image uses an Alpine Python runtime to keep the bundled sandbox image smaller. It keeps only the runtime packages needed by the sandbox wrapper and installs PyPI dependencies with `--prefer-binary` so native wheels are used when available while pure-Python source distributions can still install.

The host CLI opens your host browser to:

```text
http://127.0.0.1:8000
```

The browser launch happens on the host side, while the web server inside the container is started with its own browser launch disabled. The container binds the web server to `0.0.0.0` internally and publishes it to `127.0.0.1:8000` on the host.

Use a different host port when needed:

```bash
pbi-agent sandbox web --port 9001
```

## Run One Prompt

```bash
pbi-agent sandbox run --prompt "Summarize this repository."
```

Images and project scoping work the same way as normal `run`:

```bash
pbi-agent sandbox run --prompt "Read this diagram" --image docs/flow.png
pbi-agent sandbox run --prompt "Inspect this package" --project-dir packages/api
```

## Credentials

The sandbox wrapper passes through `PBI_AGENT_*` variables and the provider key variables used by pbi-agent, such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `ANTHROPIC_API_KEY`.

You can also pass an explicit env file:

```bash
pbi-agent sandbox --env-file .env.sandbox web
```

Do not bake provider keys into the Docker image. Keep secrets in environment variables, Docker secrets, or an env file outside version control.

## Storage

The repository is mounted under a stable per-repository path below `/workspace`. By default it is writable, so file edits inside the sandbox change the host repository directly.

If the host has `~/.pbi-agent`, the sandbox bind-mounts that directory at:

```text
/home/pbi/.pbi-agent
```

That lets the VM load your existing saved provider config, model profiles, auth state, sessions, and run history.

If `~/.pbi-agent` does not exist yet, pbi-agent uses a per-repository named Docker volume at the same container path. In both cases, pbi-agent internal state stays out of the repository while persisting across container restarts.

## Safer Inspection Mode

Use `--read-only-repo` to mount the repository read-only:

```bash
pbi-agent sandbox --read-only-repo run --prompt "Review this repo without editing files."
```

This mode is useful for inspection, but file-edit tools and commands that write to the repo will fail.

## Security Boundary

The sandbox uses a non-root container user, drops Linux capabilities, sets `no-new-privileges`, limits processes and memory, uses a read-only image filesystem, and provides writable temporary storage through `tmpfs`.

It does not mount the Docker socket, the host home directory, an SSH agent, or broad host filesystem paths.

Important limitation: a writable bind mount gives the agent full write access to the mounted repository. Docker Desktop isolates the process from the host OS, but it does not protect files that you intentionally mount writable.

The first version uses Docker Desktop's normal network. Strict domain-level egress allowlisting is not built in; add a proxy or custom Docker network policy if your environment requires that.
