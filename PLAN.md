# Plan: `$` Skill Tags in Web Composer

## Summary
- Add Codex-inspired `$` skill suggestions to the chat composer while keeping `@` file suggestions and `/` commands separate.
- `$` suggestions should list installed project skills from `.agents/skills/*/SKILL.md`, insert `$skill-name`, and make the runtime prompt explicitly treat `$skill-name` as an explicit skill request.
- Preserve the hardened `@` behavior: file suggestions must continue scanning all workspace subfolders except gitignored file/folder paths, including non-gitignored dot folders such as `.agents`.

## Checklist
- [X] Backend skill search API
  - [X] Add an internal skill-mention search helper using `discover_installed_project_skills(workspace=...)`; return installed skills sorted by name/path for empty queries and ranked by name/description for non-empty queries.
  - [X] Add system API models `SkillMentionItemModel { name, description, path }` and `SkillMentionSearchResponse { items }`.
  - [X] Add `GET /api/skills/search?q=&limit=` in the system routes, wired through `CatalogsMixin.search_skill_mentions()`; reuse existing `MentionQuery` and `MentionLimitQuery` bounds.
  - [X] Leave `/api/config/skills` install/list endpoints unchanged.
- [X] Runtime skill-tag semantics
  - [X] Update `skill_loading_rules` in `agent/system_prompt.py` so `$<skill-name>` in user input is treated as an explicit request to use that skill, matching after stripping `$` and loading the catalogued `SKILL.md` before applying it.
  - [X] Do not add new DB fields, migrations, or message schemas for this pass; submitted text remains plain text containing `$skill-name`.
- [X] Frontend API/types
  - [X] Add `SkillMentionItem`/`SkillMentionSearchPayload` types and `searchSkillMentions(query, limit)` in `webapp/src/api.ts`.
  - [X] Regenerate `webapp/src/api-types.generated.ts` with `bun run web:api-types` and keep API type-codegen tests current.
- [X] Composer behavior
  - [X] Add a `skill` completion mode alongside existing file and slash modes.
  - [X] Add a token-under-cursor parser for `$` tags: trigger at token boundaries, allow bare `$` to show all skills, ignore mid-word `$`, shell-variable forms such as `$(` / `${` / `$1`, and disable skill suggestions while the composer is in `!` shell mode.
  - [X] Search skills with the same debounce/request-id stale-response guard used by current completions; no polling is needed.
  - [X] Render skill suggestions under `Skill suggestions`, showing `$name`, description, and a `skill` badge; empty/error text should be `No matching skills`, `Searching skills...`, and `Unable to load skills`.
  - [X] Insert the selected item as `$skill-name ` via Enter, Tab, or click; Escape dismisses until the `$` token changes.
  - [X] Keep `/` slash command behavior and `@` file suggestion behavior unchanged.
- [X] Tests and assets
  - [X] Add backend unit/API coverage for skill search ranking, empty-query ordering, skipped invalid skills, and `/api/skills/search` response shape.
  - [X] Update system-prompt tests to assert `$<skill-name>` is documented as explicit skill invocation.
  - [X] Update frontend API tests for `searchSkillMentions()` URL/query handling.
  - [X] Extend `Composer.test.tsx` for `$` popup open/filter/select/click, stale-response discard, Escape dismissal, no popup for shell variables or shell mode, and no regression for `/` and `@` completions.
  - [X] Rebuild static web assets with `bun run web:build` after frontend changes, preserving unrelated pre-existing dirty static asset changes.

## Public API / Interface Changes
- New endpoint: `GET /api/skills/search?q=<query>&limit=<n>` returns `{ items: [{ name, description, path }] }` for installed project skills.
- New frontend helper: `searchSkillMentions()` returns the full skill-search payload.
- Composer trigger map becomes `/` = commands, `@` = files, `$` = skills.
- System prompt rules explicitly define `$skill-name` as an explicit skill invocation cue.

## Validation
- [X] `bun run web:api-types` — passed.
- [X] Focused Python: `uv run pytest -q --tb=short -x tests/test_skill_mentions.py tests/test_web_serve.py::test_skill_search_endpoint_returns_installed_project_skills tests/test_system_prompt.py::test_get_system_prompt_with_project_skills tests/test_api_types_codegen.py` — passed.
- [X] Focused frontend: `bun run test:web -- webapp/src/components/session/Composer.test.tsx webapp/src/api.test.ts` — passed.
- [X] Static/frontend checks: `bun run lint`, `bun run typecheck`, `bun run web:build` — passed.
- [X] Python checks for touched surface: `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright` — passed.
- [-] Optional broad check if time allows: `uv run pytest -q --tb=short -x` — skipped; prior known unrelated CLI catalog failure.

## Assumptions / Scope
- Only installed project skills are suggested; remote skill catalog search/install remains in Settings.
- `$` is for skills only in this pass; plugin/app/sub-agent `$` mentions are out of scope.
- Skill tags rely on existing progressive-disclosure loading by the agent; the UI does not inline skill instructions into the message.
- Do not regress existing `@` file scanning: all non-gitignored files under all subfolders remain suggestible, including non-gitignored dot paths.
- Preserve unrelated current dirty files and prior static app asset churn; do not revert `MEMORY.md`, `TODO.md`, input-mention/scan tests, or existing static bundle changes.
