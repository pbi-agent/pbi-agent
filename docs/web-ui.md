---
title: 'Web UI'
description: 'Browser-based sessions, navigation, settings, and interactive workflows in pbi-agent.'
---

# Web UI

Running `pbi-agent` without a subcommand starts the browser UI:

```bash
pbi-agent
```

The web UI is the default interactive workspace. It combines live chat sessions, local shell execution, saved configuration, Kanban task automation, and observability in one local FastAPI/Vite app.

## Primary navigation

| Area | Purpose |
| --- | --- |
| Sessions | Start or resume agent conversations, use `@file` mentions, upload images, run shell commands, and inspect run history. |
| Kanban | Manage task cards across configurable workflow stages and start automated task runs. |
| Dashboard | Review run observability, cost/token totals, duration, errors, and provider/model breakdowns. |
| Settings | Configure providers, model profiles, ChatGPT account auth, and project command discovery. |

If provider setup is incomplete, the app sends you to **Settings** first so you can create a provider and model profile.

## Sessions

Sessions are live conversations bound to the current workspace. A session can start without a saved history record, then becomes bound once the first model turn is persisted.

Session features include:

- A session sidebar for saved and active sessions.
- A model-profile selector for choosing the runtime profile before a turn.
- `@file` mention autocomplete for workspace files.
- Slash-command autocomplete for built-in and project commands.
- Image uploads from the `+` action menu or clipboard when the provider supports images.
- Shell command mode with `!command` for local commands that do not call the model.
- A stop/interrupt control while the model is processing.
- Run history attached to the saved session.

See [Session Commands](/session-commands) for the full composer syntax reference.

## Saved sessions and resume behavior

Saved sessions appear in the Sessions sidebar. Reopening a session restores the provider checkpoint when possible; otherwise pbi-agent replays the visible history needed to continue. The session timeline shows user turns, assistant turns, local tool activity, image attachments, shell output, and run metadata.

Starting a new session resets the provider conversation state while keeping the current runtime settings.

## Settings

The Settings page manages persistent local configuration under `~/.pbi-agent/`:

- Providers hold connection settings such as provider kind, API key, auth mode, and endpoint URLs.
- Model profiles hold runnable model/runtime settings tied to one saved provider.
- The active default profile is used when a session or run does not specify another profile.
- Project commands are discovered from `.agents/commands/*.md` and listed for visibility.

See [Providers](/providers) and [Model Profiles](/model-profiles) for setup details.

## Images

For OpenAI, Google, Anthropic, and Azure-compatible image-capable endpoints, the web UI supports explicit image inputs:

- Use the composer `+` action menu to choose local image files.
- Paste images from the clipboard.
- Mention workspace images with `@path/to/image.png` in normal prompts.

Supported image formats are `.png`, `.jpg`, `.jpeg`, and `.webp`.

## Local-only commands

Some inputs are handled by the web app/session runtime without a model request:

- `!command` runs a workspace shell command.
- `/skills`, `/mcp`, and `/agents` show discovered project catalogs.
- `/reload` refreshes workspace instructions and the web file-mention cache.
- `/compact` summarizes long session history for future turns.

These commands are documented in [Session Commands](/session-commands).

## Related pages

- [Kanban Dashboard](/kanban-dashboard)
- [Model Profiles](/model-profiles)
- [Session Commands](/session-commands)
- [Dashboard observability](#primary-navigation)
