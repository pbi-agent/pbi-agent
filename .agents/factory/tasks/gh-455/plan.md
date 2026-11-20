# Plan: omit tool choice and tool-only fields on tool-less provider requests (gh-455)

## Summary
Enhance prompt (and context compaction) open a provider with `allowed_tools=()` and an empty `ToolCatalog()`, so `self._tools == []`. The GitHub Copilot Chat Completions body still sends `"tools": [], "tool_choice": "auto"`, which Copilot rejects with a 400. ChatGPT/Codex sends `tool_choice: "auto"` with no tools. The Responses-family builders (OpenAI API, Codex, Copilot Responses, xAI) also send `parallel_tool_calls: true` with `tools: []`.

Fix rule, applied to every builder that does not already follow it: **when the provider's tool list is empty, send no `tools`, no tool choice and no `parallel_tool_calls`.** This follows the existing precedent in the generic `ChatCompletionsProtocol` (`79a5a6bb`) and the GCP Responses, GCP Anthropic and generateContent builders. When tools are present, the request body stays byte-for-byte identical, key order included.

One group. About 5 source files and 5 test files. No API, interface, type, settings, frontend or docs changes.

## Key Changes
Pattern for every builder: build the body exactly as it is built today, then remove the tool fields only when the tool list is empty (`body.pop(...)`, or skip a conditional insertion). Do not reorder or reconstruct the dict. That way tool-using bodies keep the same keys in the same order, so their JSON is identical.

Per-backend decisions:
- **GitHub Copilot Chat Completions** (`github_copilot_provider.py` `_GitHubCopilotChatCompletionsProvider._http_request`): when `self._tools` is empty, drop both `tools` and `tool_choice`. This is the reported bug. It matches the generic protocol, which this class's own copy of the body never picked up. Do not add `parallel_tool_calls`; it is not sent today.
- **Responses family** (`openai_provider.py` `_build_request_body`; covers OpenAI API, ChatGPT/Codex over HTTP and WebSocket, and Copilot Responses through its `super()` override): when `self._tools` is empty, drop `tools` and `parallel_tool_calls`, and skip the `tool_choice` insertion. The guard becomes `if self._tools and request_options.tool_choice is not None`. `ResponsesRequestOptions.tool_choice="auto"` in `chatgpt_codex_backend.py` stays as it is, so Codex tool-using turns are unchanged. No change is needed in the Copilot Responses override.
  - Reasoning: OpenAI's Chat Completions API rejects `parallel_tool_calls` without `tools`. Whether the Copilot Responses proxy and the Codex backend accept it cannot be verified offline, and GCP Responses already guards it. Dropping all three fields is the conservative choice.
- **xAI** (`xai_provider.py` `_build_request_body`): when `self._tools` is empty, drop `tools` and `parallel_tool_calls`. xAI never sends a tool choice.
- **Google Gemini Interactions** (`google_provider.py` `_build_request_body`): when `self._tools` is empty, drop `tools`. This backend has no tool choice or parallel field. The change keeps the rule uniform with GCP and generateContent. It is safe because tool-less callers (enhance, compaction) use a fresh provider with no `previous_interaction_id` and no tool history.
- **Anthropic Messages** (`protocols/anthropic_messages.py` `build_messages_body`; used by Anthropic and Azure Anthropic): when `tools` is empty, drop `tools`. `tool_choice` is never set here. The change is safe for the same reason: tool-less callers send only a text transcript, with no `tool_use` blocks. Top-level `cache_control` stays.
- **Unchanged**: generic, Azure chat and GCP chat (`ChatCompletionsProtocol`), GCP Responses, GCP Anthropic and generateContent all already omit tool fields when there are no tools.

Out of scope, leave as is: enhancement prompt text, error display, the `tool_catalog or ToolCatalog.from_builtin_registry()` fallback in provider constructors, and how tools are wired for tool-using turns.

## Test Plan

### Trap
An empty `ToolCatalog()` is falsy (`__bool__`/`__len__` in `tools/catalog.py`), so providers silently fall back to the builtin registry. Every no-tools test must mirror production:
- settings with `allowed_tools=()`
- `tool_catalog=ToolCatalog()`
- a precondition `assert provider._tools == []`

### Reproduce (bug_fix `reproduce`)
Write the new Copilot chat test first and run it before touching `src/`:
`uv run pytest tests/test_github_copilot_provider.py::test_github_copilot_chat_completions_omits_tool_fields_without_tools`
It must fail on `tool_choice == "auto"` / `tools == []`. Paste the failure output into the build stage record. Do the same for the other new tests; each fails before the fix because the field is present.

### Byte-for-byte characterization (AC3)
Before editing `src/`, write a scratch script in the session scratchpad. Extend the triage script `bodies_gh455.py` in that scratchpad, and keep it out of the repo. With the default builtin tools (no `allowed_tools=()`), it dumps `json.dumps(body)` for each changed builder:
- Copilot chat: capture through a fake `urlopen` on `request_turn`
- OpenAI API, ChatGPT/Codex, Copilot Responses, xAI and Google: `_build_request_body`
- Anthropic: `build_messages_body` with the provider's tools

Save the output, re-run the script after the fix, and confirm with `diff` that nothing changed. Record the result in the build stage file.

### Regression tests (bug_fix `regression_test`, AC2)
New no-tools request-shape tests:
- `tests/test_github_copilot_provider.py`:
  - `test_github_copilot_chat_completions_omits_tool_fields_without_tools`: `model="claude-sonnet-4"`, fake `urlopen`, `request_turn`. Assert that `tools` and `tool_choice` are absent and that `messages`, `max_tokens`, `stream` and `model` are present. Model it on `tests/test_generic_provider.py::test_generic_request_turn_omits_empty_tools`.
  - `test_github_copilot_responses_omits_tool_fields_without_tools`: `model="gpt-5.4"`, through `_delegate._build_request_body`. Assert there is no `tools`, `parallel_tool_calls` or `tool_choice`.
- `tests/test_openai_provider.py`:
  - `test_openai_build_request_body_omits_tool_fields_without_tools`: parametrized over the OpenAI API URL and `OPENAI_CHATGPT_RESPONSES_URL` (Codex). Assert there is no `tools`, `parallel_tool_calls` or `tool_choice`, and that the other Codex contract keys (`stream`, `store`, `include`, `instructions`) are still present.
- `tests/test_xai_provider.py`:
  - `test_xai_build_request_body_omits_tool_fields_without_tools`: no `tools` and no `parallel_tool_calls`.
- `tests/test_google_provider.py`:
  - `test_google_build_request_body_omits_tools_without_tools`: no `tools`.
- `tests/test_anthropic_provider.py`:
  - `test_anthropic_request_body_omits_tools_without_tools`: build through the provider (`AnthropicProvider` with an empty tool list, calling `build_messages_body` with `provider._tools`). Assert there is no `tools` and no `tool_choice`, and that `cache_control`, `messages` and `system` are kept.

Keep or add tool-using shape assertions (AC3):
- Existing assertions must still pass: `tests/test_openai_provider.py:268` and `:296` (`parallel_tool_calls is True`, Codex `tool_choice == "auto"`, non-empty function tools) and `tests/test_xai_provider.py:180` (`parallel_tool_calls`).
- Add `body["tool_choice"] == "auto"` and non-empty `body["tools"]` to `test_github_copilot_non_openai_model_uses_chat_completions`. Today it checks neither.
- Add non-empty `tools` and `parallel_tool_calls is True` to `test_github_copilot_openai_model_uses_responses_headers_and_omits_max_tokens`.
- Add non-empty `body["tools"]` to `test_google_build_request_body_uses_interactions_shape` and to one Anthropic tool-using request test (for example `test_anthropic_request_turn_preserves_history_and_wraps_tool_results`), if they do not already assert it.

### Python surface validation (AC4)
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run basedpyright`
- the targeted provider test files above, then the full `uv run pytest`

If the known flaky `test_lost_manager_lease_rejects_new_live_sessions` is the only failure, follow the AGENTS.md rerun rule.

### Live check (AC1, verify skill)
A `github_copilot` provider `copilot` and the active web profile `opus-5-5` (Copilot `claude-opus-5.5`, which uses the Chat Completions path) are in `~/.pbi-agent/config.json`. `web.prompt_enhancement_profile_id` is null, so enhance uses the default runtime, which is the active profile.

1. Follow the verify skill "Scratch server" steps:
   - make a DB copy in the scratchpad
   - run `bun run web:build` (Python-only change, but the server serves the bundle)
   - start from a scratch workspace on a free 74xx port with `PBI_AGENT_SESSION_DB_PATH` set to the copy
2. Confirm with `curl /api/bootstrap` that the active profile resolves to the Copilot profile.
3. `curl -fsS -X POST http://127.0.0.1:<p>/api/prompt/enhance -H 'content-type: application/json' -d '{"text":"fix teh grammer in readme and make it clear"}'` must return HTTP 200 with non-empty rewritten `text`, and no 400 or tools error.
4. Optionally, repeat in the UI with the wand button or Ctrl+Space on a draft.
5. Optional extra coverage: `POST /api/sessions` with `{"profile_id":"worker-pro"}` (ChatGPT/Codex) on the scratch DB, then enhance with that `session_id`. This checks that Codex accepts the slimmer body.
6. Before the fix, the same curl against the Copilot profile should reproduce the 400. Run it if cheap; it is not required.
7. Stop the server by PID or port, and record the port, the profile, and the response status and excerpt.

## Assumptions
- No backend needs a tool-less request to carry `tools: []`. This is supported by the generic and GCP precedent and by Enhance/compaction never sending tool history. If the live Codex check shows Codex requires `tools`, restore only `tools: []` for Codex (still without `tool_choice` or `parallel_tool_calls`) and record it.
- "Byte-for-byte unchanged" means the serialized JSON body is identical for tool-using requests. The scratch `diff` proves this, alongside dict-level tests.
- Compaction is fixed by the same change (same code path). It gets no separate test; the provider-level tests cover the wire shape.
- The memory and TODO updates are done by the main agent, not this stage.

plan: ready
