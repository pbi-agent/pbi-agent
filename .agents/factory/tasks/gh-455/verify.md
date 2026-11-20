# Verify gh-455

verify: pass

## Full validation (working tree after fix-1)
- `uv run ruff check .`: All checks passed!
- `uv run ruff format --check .`: 1064 files already formatted (triage.md reformatted by conductor at build; ruff formats Python fences in .md)
- `uv run basedpyright`: 0 errors, 0 warnings, 0 notes
- `uv run pytest`: 2533 passed, 9 skipped in 75.79s
- No frontend or docs change: web/docs checks not required.

## Live check (full; fix-1 changed `github_copilot_provider.py` after the build live check)
Scratch server per the verify skill: DB backup copy with lease cleared, cwd `$S/ws`, `PBI_AGENT_SESSION_DB_PATH=$S/sessions.db`, port 7456 (`$S` = session scratchpad `/verify`). Bootstrap: `provider github_copilot`, `profile_id opus-5-5`, `model claude-opus-5.5` (Copilot Chat Completions path = buggy path).

1. Enhance, no session, the issue's draft:
   `POST /api/prompt/enhance {"text":"test horizontal scroling for a table with a very long colum in the chat"}`
   → HTTP 200 in 1.26s, `{"text":"Test horizontal scrolling for a table with a very wide column in the chat.","session":null}`
2. Enhance with session `0cd5f337…` (traced): HTTP 200 in 0.97s, `"Fix the grammar and typos in the README and improve its clarity."`
   `model_call` → `https://api.githubcopilot.com/chat/completions`, status 200, success 1, error none; request payload keys `max_tokens, messages, model, stream` (no `tools`, `tool_choice`, `parallel_tool_calls`).
3. Tool-using Copilot turn (path changed by fix-1): `pbi-agent --profile-id opus-5-5 run -p "Use the shell tool to run: cat note.txt..." --allowed-tools shell` in `$S/ws2` with scratch DB → printed `alpha-beta-42`, exit 0. Both `model_call`s → `/chat/completions` 200; payload keys `max_tokens, messages, model, stream, tool_choice, tools` (2 tools, `tool_choice: auto`); one `shell` tool_call succeeded.
Server stopped with `fuser -k 7456/tcp`; port free, no server process.

## Acceptance criteria
1. Live Copilot Enhance prompt succeeds without the 400: **confirmed** (checks 1-2 above; wire body has no tool fields).
2. No provider sends tool choice without tools; no-tools tests per changed provider pass: **confirmed**. Diff: Copilot chat now uses the shared chat-completions builder (empty-tools guard), OpenAI Responses builder (OpenAI, Codex, Copilot Responses), xAI, Google Interactions, Anthropic Messages pop `tools`/`parallel_tool_calls` and skip tool choice when tools are empty. New no-tools tests in `tests/test_{github_copilot,openai,xai,google,anthropic}_provider.py` (failed before the fix per build.md, pass now).
3. Tool-using requests unchanged: **confirmed**. Raw sha256 unchanged for the other builders, sorted-JSON identical for Copilot chat (build.md, fix-1.md); live tool turn (check 3); full pytest green.
4. Repo checks for touched surfaces pass: **confirmed** (above).
