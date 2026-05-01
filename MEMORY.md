# MEMORY.md

## Metadata
- Last compacted: 2026-05-01
- Scope: durable repo memory + active-day task events.
- Format: only `Metadata`, `Long-Term Memory`, `Detailed Task Events`.

## Long-Term Memory
- Memory: token-efficient; keep durable decisions/follow-ups only, not logs.
- Workflow: no commit/push/merge/PR unless asked. Use session-only `TODO.md`; markers `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`. Shell from workspace root.
- Validate touched surface: Python Ruff+pytest; frontend Bun tests/lint/typecheck/build; docs build. Note skipped/hung checks.
- Architecture: CLI `src/pbi_agent/__main__.py` -> `src/pbi_agent/cli.py`; default command `web`; backend FastAPI `src/pbi_agent/web/`; frontend Vite React `webapp/`.
- API changes: align routes/schemas/session manager with `webapp/src/api.ts` + `webapp/src/types.ts`.
- Constraints: provider/tool HTTP via `urllib.request`; internal data in `~/.pbi-agent/`; no migrations/backcompat.
- Tools: built-in `python_exec`, `list_files`, `search_files` removed; use shell (`rg --files`, `find`, `rg -n`) and Python as needed.
- Project imports: top-level `skills`, `commands`, `agents`; public catalogs under `pbi-agent/{skills,commands,agents}`; local install to `.agents/...`.
- Sub-agents: `.agents/agents/*.md`; frontmatter only `name`/`description`; child model from active profile/CLI + `sub_agent_model`.
- Local commands: `plan` no questions; `review` Markdown; `fix-review` stops on `No findings.`; `ship-task` branch/merge helpers; `release` needs explicit publish wording and no history rewrite after PR unless approved.
- Release docs: `release-writing` skill governs releases; changelog index `docs/changelog/index.md`, files `docs/changelog/v<version>.md`, VitePress sidebar links releases; release retrospective added validation triage + publish verification + continuation gate safety.
- Branding: public copy = local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`; logo `src/pbi_agent/web/static/logo.jpg`.
- Web/session: saved sessions reopen via `resume_session_id`; SQLite leases use `BEGIN IMMEDIATE`/`busy_timeout`; duplicate manager startup emits one warning.
- Session compaction: clear completed `previous_id`; resume restores persisted user/assistant history; compaction includes unanswered trailing user turns and same-turn tool exchanges.
- Providers: OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt; Codex transport is WebSocket-only (`chatgpt_codex_backend.py`), no unsupported compression.
- Web UI: prefer shadcn tokens/components; overlays use shared readable spacing; large modals need safe gutters + inner scroll.
- Timeline: work runs coalesce thinking/tool groups; running closed by default; final assistant closes current collapsibles; file-edit results share `FILE_EDIT_TOOL_NAMES`.
- Syntax highlighting: `read_file` uses lazy Shiki code block; root `package.json` pins exact `shiki` `4.0.2`.
- v0.1.0 shipped.
- Kanban task images: stored as task `image_attachments_json`, task create/update accepts `image_upload_ids`, uploads reuse `~/.pbi-agent/web_uploads` + `/api/live-sessions/uploads/{id}` previews, initial task run sends images only with first full prompt.
- Provider history restore preserves user message image attachments for image-capable providers (OpenAI/ChatGPT, Anthropic, Google) by reloading upload IDs from `~/.pbi-agent/web_uploads`.

## Detailed Task Events
## 2026-05-01
- Added Kanban task image attachments: backend task upload endpoint + persisted attachments, task create/update image IDs, initial task run image plumbing, frontend TaskModal upload/preview/remove, card image count, docs update. Validation: Ruff check/format targeted, pytest `tests/test_session_store.py` + `tests/test_web_serve.py`, `bun run typecheck`, targeted web tests, `bun run lint`, `bun run web:build`, `bun run docs:build` passed.
- Ensured existing SQLite DBs add missing `image_attachments_json` on `kanban_tasks` (messages already covered) and added regression coverage for old message/task tables. Validation: `uv run pytest tests/test_session_store.py`, targeted Ruff check/format passed.
- Fixed review findings for Kanban task images: continuation/stage handoff user messages now persist/publish no task images, and deleting a linked session preserves upload files still owned by tasks. Validation: targeted Ruff check/format and `uv run pytest tests/test_web_serve.py::test_auto_started_stage_prompt_is_visible_while_running tests/test_web_serve.py::test_delete_session_endpoint_preserves_task_owned_uploads -q` passed.
- Fixed restored session history dropping first-turn images in later task turns: OpenAI/ChatGPT, Anthropic, and Google provider `restore_messages()` now rebuild user image content from persisted upload IDs. Checked session `f164fd1b53a14623a58b25c7ea3da6da` now rebuilds later payload history with the first user image. Validation: targeted Ruff check/format and provider tests passed.
- Added delete confirmation hover styling via `delete-confirm-modal__confirm` on shared `DeleteConfirmModal`, plus component coverage for destructive action class and pending disabled label. Validation: `bun run test:web -- DeleteConfirmModal`, `bun run lint`, and `bun run typecheck` passed.
- Added delete confirmation Cancel hover styling via `delete-confirm-modal__cancel`, matching existing outline validation action hover behavior. Validation: `bun run test:web -- DeleteConfirmModal`, `bun run lint`, and `bun run typecheck` passed.
- Updated `/ship-task` command instructions to require GitHub workflow verification before merge with `gh pr checks <pr> --watch --fail-fast --interval 10`, result inspection via `gh pr checks`, and optional `gh pr view --json statusCheckRollup,mergeStateStatus,isDraft,url`. Validation: checked local `gh` help/syntax; no code tests needed for docs-only command change.
- Fixed web input mention expansion crash for overlong path candidates: parser catches filesystem `OSError` while scanning `@file` mentions, keeps resolving shorter valid file mentions before prompt prose, and returns concise warnings for overlong unresolved paths. Validation: targeted input mention/API pytest and Ruff check/format passed.
