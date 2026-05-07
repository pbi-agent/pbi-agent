---
title: 'Docker Sandbox'
description: 'Run pbi-agent inside a Docker Desktop Linux container.'
---

# Docker Sandbox

`pbi-agent sandbox` runs the whole agent process inside a Docker Desktop Linux container. The current repository is mounted under a per-repository directory below `/workspace`, and the agent runs from that mounted repository directory, so model-requested shell commands, file reads, file edits, MCP servers, and sub-agents execute inside the container instead of directly on the host.

The container path is only the execution root. Sessions, Kanban tasks, run history, and the workspace label in the web UI use the real host workspace path, so opening the same folder with or without sandbox shows the same conversation history and board.

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

Start the sandbox web server in the background with:

```bash
pbi-agent sandbox -d web
```

Docker prints the started container id. Stop it later with:

```bash
docker stop <container-id>
```

When installed from PyPI, `pbi-agent sandbox` builds a small sandbox image from the Dockerfile bundled inside the installed package. The CLI reads its installed package version and passes it as `PBI_AGENT_VERSION`, so the image installs the matching PyPI package version with:

```dockerfile
python -m pip install --prefer-binary "pbi-agent==${PBI_AGENT_VERSION}"
```

The image uses an Alpine Python runtime to keep the bundled sandbox image smaller. It keeps only the runtime packages needed by the sandbox wrapper, common workspace utilities such as `curl` and `rg` (`ripgrep`), and shared runtime libraries commonly required by user-installed tools. PyPI dependencies install with `--prefer-binary` so native wheels are used when available while pure-Python source distributions can still install.

When developing pbi-agent itself, use local source mode to test the mounted checkout inside the sandbox instead of the last published PyPI package:

```bash
uv run pbi-agent sandbox --local-source web
uv run pbi-agent sandbox --local-source run --prompt "Test this checkout."
```

Local source mode starts from the normal sandbox image, then installs the mounted repository in editable user mode before launching the requested command:

```bash
python -m pip install --user --prefer-binary -e "$PBI_AGENT_LOCAL_SOURCE"
```

That keeps the Docker sandbox behavior close to the released image while loading your current Python files from the host checkout. If package dependencies changed, rebuild the base sandbox image after publishing or expect pip to install any missing dependencies into the project-scoped sandbox home volume.

The host CLI opens your host browser to:

```text
http://127.0.0.1:7424
```

The browser launch happens on the host side, while the web server inside the container is started with its own browser launch disabled. The container binds the web server to `0.0.0.0` internally and publishes it to `127.0.0.1:7424` on the host.

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

For Git and GitHub access, the sandbox also reuses standard host account files when they exist by mounting them read-only into the container user's home: `~/.gitconfig`, `~/.config/git`, `~/.git-credentials`, `~/.ssh`, and `~/.config/gh`. That lets commits use the same Git identity and lets common SSH, credential-store, and GitHub CLI auth setups work inside the sandbox without mounting the whole host home directory.

Host-specific credential helpers such as macOS Keychain or Windows Credential Manager only work inside the Linux sandbox if the matching helper is installed there. For portable sandbox auth, use SSH keys, Git's credential-store file, or a GitHub CLI auth config that is available through those mounted paths.

You can also pass an explicit env file:

```bash
pbi-agent sandbox --env-file .env.sandbox web
```

Do not bake provider keys into the Docker image. Keep secrets in environment variables, Docker secrets, or an env file outside version control.

## Storage

The repository is mounted under a stable per-repository path below `/workspace`. By default it is writable, so file edits inside the sandbox change the host repository directly. The web UI still displays the host workspace path instead of the internal `/workspace/<id>` path.

The sandbox creates `~/.pbi-agent` on the host if needed, then bind-mounts that directory at:

```text
/home/pbi/.pbi-agent
```

That lets the VM load your existing saved provider config, model profiles, auth state, sessions, Kanban tasks, and run history. Sandbox and non-sandbox runs share those records because the sandbox passes the host workspace path into the container as the workspace identity.

The image filesystem is read-only, but the sandbox mounts the entire container user home directory at `/home/pbi` from a per-repository named Docker volume. Anything an installer or package manager writes under `/home/pbi` is writable and persistent across sandbox restarts for the same repository; this is a generic home volume, not a folder-by-folder allowlist.

The container process `PATH` includes the standard user-local executable directory, `/home/pbi/.local/bin`. Shell tool commands also run through a sandbox bootstrap that sources readable user profile files under `/home/pbi` and discovers `bin` directories under the persistent home volume. The bootstrap also refreshes discovered `bin` paths when Bash sees a missing command, so install-and-run commands can pick up newly created tool directories. This keeps installer-specific paths out of the image while still making tools installed into locations such as `.bun/bin` or `.cargo/bin` visible to non-login shell commands.

The sandbox still provides temporary storage for `/tmp` and uses temporary `/home/pbi/.cache` storage so caches do not accumulate in the persistent home volume.

For example, inside a sandbox session an agent shell command can install and use uv with:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
uv --version
```

Those local tools, installer receipts, and package-manager directories stay available when you start `pbi-agent sandbox` again from the same repository. Delete the project-scoped Docker home volume if you want to reset them.

## Safer Inspection Mode

Use `--read-only-repo` to mount the repository read-only:

```bash
pbi-agent sandbox --read-only-repo run --prompt "Review this repo without editing files."
```

This mode is useful for inspection, but file-edit tools and commands that write to the repo will fail.

## Security Boundary

The sandbox uses a non-root container user, drops Linux capabilities, sets `no-new-privileges`, limits processes and memory, uses a read-only image filesystem, and limits writable home storage to project-scoped Docker volumes plus temporary `tmpfs` paths.

It does not mount the Docker socket, the host home directory, an SSH agent, or broad host filesystem paths. When available, only the selected Git and GitHub account paths listed above are mounted from the host home, and they are mounted read-only.

Important limitation: a writable bind mount gives the agent full write access to the mounted repository. Docker Desktop isolates the process from the host OS, but it does not protect files that you intentionally mount writable.

The first version uses Docker Desktop's normal network. Strict domain-level egress allowlisting is not built in; add a proxy or custom Docker network policy if your environment requires that.
