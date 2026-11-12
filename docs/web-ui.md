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
| Settings | Configure your global profile, providers, model profiles, speech-to-text, account auth, and project skill/command installs. |

If provider setup is incomplete, the app sends you to **Settings** first so you can create a provider and model profile.

## Sessions

Sessions are live conversations bound to the current workspace. A session can start without a saved history record, then becomes bound once the first model turn is persisted.

Session features include:

- A session sidebar for saved and active sessions.
- A model-profile selector for choosing the runtime profile before a turn.
- An **Include tool history** toggle in the session topbar. It is off by
  default and remembered globally. When enabled before continuing a saved
  session, pbi-agent includes prior tool calls, tool arguments, tool results, and
  useful tool errors in the resumed model context.
- `@file` mention autocomplete for workspace files.
- Slash-command autocomplete for built-in and project commands.
- Image uploads from the `+` action menu or clipboard when the provider supports images.
- Voice dictation from the microphone when a speech-to-text provider is selected.
- Shell command mode with `!command` for local commands that do not call the model.
- A stop/interrupt control while the model is processing.
- Run history attached to the saved session.

See [Session Commands](/session-commands) for the full composer syntax reference.

### Session titles

A new session is first titled with the start of its first message. When the
local title model is available, that title is replaced a moment later by a
one-line summary generated on your machine; nothing is sent to a provider for
it, and a title you edit yourself is never overwritten.

The first time `pbi-agent web` starts, it downloads the title model
([oot-oneliner](https://huggingface.co/oot-ai/oot-oneliner-GGUF), about 1.1 GB,
LFM license) and the official prebuilt
[llama.cpp](https://github.com/ggml-org/llama.cpp) build for your platform
(13-25 MB) in the background into `~/.pbi-agent/title-model`. Both are pinned
to one version and verified against a SHA-256 checksum, and an interrupted
download resumes on the next start. Until they are present, and on platforms
without a prebuilt llama.cpp build, titles stay as the start of the first
message. Set `PBI_AGENT_LOCAL_TITLES=0` to turn this off.

## Saved sessions and resume behavior

Saved sessions appear in the Sessions sidebar. Reopening a session restores the provider checkpoint when possible; otherwise pbi-agent replays the visible history needed to continue. The session timeline shows user turns, assistant turns, local tool activity, image attachments, shell output, and run metadata.

By default, saved-session continuation sends prior user and assistant messages
without previous tool-call exchanges. Turn on **Include tool history** before
submitting the next message if the agent should see previous tool calls/results
as model context. The toggle affects the new saved-session run that starts from
that submission; already-active live runs keep their current in-memory context.

Starting a new session resets the provider conversation state while keeping the current runtime settings.

## Settings

The Settings page manages persistent local configuration under `~/.pbi-agent/`:

- Profile stores your preferred name, role, background, collaboration
  preferences, and global instructions once for every workspace. Main agents and
  sub-agents receive this context when a new or reloaded session starts.
- Providers hold connection settings such as provider kind, API key, auth mode, endpoint URLs, and Google Cloud project/location values.
- Model profiles hold runnable model/runtime settings tied to one saved provider.
- The active default profile is used when a session or run does not specify another profile.
- Speech-to-text selects the saved provider used for web UI dictation.
- Project skills, commands, and agents can be installed from official catalogs, GitHub sources, or server-side local paths.

Profile content becomes part of the system prompt and is sent to the model
provider used by the session. Avoid storing secrets or other information you do
not want sent to that provider.

See [Providers](/providers), [Model Profiles](/model-profiles), and
[Speech-to-text](/speech-to-text) for setup details.

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
- `/status` opens a visual usage report with token, cost, cache, context, sub-agent, and activity metrics without calling the model.
- `/compact` summarizes long session history for future turns.

These commands are documented in [Session Commands](/session-commands).

## Related pages

- [Kanban Dashboard](/kanban-dashboard)
- [Model Profiles](/model-profiles)
- [Speech-to-text](/speech-to-text)
- [Session Commands](/session-commands)
- [Dashboard observability](#primary-navigation)
