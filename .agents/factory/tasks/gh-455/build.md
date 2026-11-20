build: checks-pass

# Build: gh-455 (bug_fix, risk high)

Implemented plan.md (single group) end to end. The rule is now applied to every builder that did not already follow it: when the provider's tool list is empty, the request carries no `tools`, no tool choice and no `parallel_tool_calls`. Tool-using request bodies are byte-for-byte identical (same keys, same order, same serialized JSON). The live Copilot Enhance prompt call returns HTTP 200 with rewritten text, and the recorded wire body has no tool fields.

## Pre-existing workspace state
- `git status --short` at start: ` M TODO.md`, `?? .agents/factory/tasks/gh-455/`. Both are unrelated to this build and were left untouched (apart from writing this build.md).

## Changed files
Source (16 insertions, 1 deletion):
- `src/pbi_agent/providers/github_copilot_provider.py`: `_GitHubCopilotChatCompletionsProvider._http_request` pops `tools` and `tool_choice` when `self._tools` is empty. This is the reported bug.
- `src/pbi_agent/providers/openai_provider.py`: `_build_request_body` pops `tools` and `parallel_tool_calls` when `self._tools` is empty. `tool_choice` is inserted only in the `elif` branch, i.e. only when tools exist. This covers the OpenAI API, ChatGPT/Codex (HTTP and WebSocket) and Copilot Responses (through its `super()` override). `chatgpt_codex_backend.py` is unchanged.
- `src/pbi_agent/providers/xai_provider.py`: `_build_request_body` pops `tools` and `parallel_tool_calls` when there are no tools.
- `src/pbi_agent/providers/google_provider.py`: `_build_request_body` pops `tools` when there are no tools.
- `src/pbi_agent/providers/protocols/anthropic_messages.py`: `build_messages_body` pops `tools` when the list is empty. This covers Anthropic and Azure Anthropic. Top-level `cache_control` is kept.

The pattern is the same in every builder: build the dict exactly as before, then `pop` the fields only when the tool list is empty. Tool-using dicts are never rebuilt or reordered.

Tests:
- `tests/test_github_copilot_provider.py`:
  - new `test_github_copilot_chat_completions_omits_tool_fields_without_tools` (`claude-sonnet-4`, fake `urlopen`, `request_turn`)
  - new `test_github_copilot_responses_omits_tool_fields_without_tools` (`gpt-5.4`, `_delegate._build_request_body`)
  - `ToolCatalog` import
- `tests/test_openai_provider.py`:
  - new `test_openai_build_request_body_omits_tool_fields_without_tools`, parametrized `[openai-api, chatgpt-codex]`. It also asserts that the Codex contract keys `stream`/`store`/`include`/`instructions`/`prompt_cache_key` are still present.
  - `test_openai_build_request_body_uses_http_responses_shape` now also asserts non-empty `tools` and no `tool_choice`.
- `tests/test_xai_provider.py`:
  - new `test_xai_build_request_body_omits_tool_fields_without_tools`
  - `test_xai_build_request_body_omits_unsupported_reasoning_effort` now asserts non-empty `tools`
  - `ToolCatalog` import
- `tests/test_google_provider.py`:
  - new `test_google_build_request_body_omits_tools_without_tools`
  - `test_google_build_request_body_uses_interactions_shape` now asserts non-empty `tools`
  - `ToolCatalog` import
- `tests/test_anthropic_provider.py`:
  - new `test_anthropic_request_body_omits_tools_without_tools`. It goes through `AnthropicProvider.request_turn` with a fake `urlopen`, which is stronger than the planned direct `build_messages_body` call.
  - `test_anthropic_request_turn_preserves_history_and_wraps_tool_results` now asserts that `requests[0]["tools"]` is non-empty and equals `provider._tools`
  - `ToolCatalog` import

Every no-tools test mirrors production, per the plan trap:
- `allowed_tools=()`
- `tool_catalog=ToolCatalog()`
- the precondition `assert provider._tools == []` (or `_delegate._tools` for Copilot)

Scratch scripts (not in the repo), all in `/tmp/claude-1000/-home-drod-workspace-pbi-agent/d9ece85a-34ce-4131-a7e4-9da1b38cf28d/scratchpad/`:
- `charz_gh455.py`: the characterization dump. Default run uses the builtin tools; the `notools` argument runs the tool-less shape.
- Saved outputs: `charz_before.txt`, `charz_after.txt`, `charz_notools_before.txt`, `charz_notools_after.txt`, `reproduce_copilot.txt`, `prefix_newtests.txt`, `pytest_full.txt`, `enhance_copilot.txt`, `enhance_copilot_session.txt`, `enhance_codex.txt`, `web.log`, `sessions.db` (scratch DB copy).

## Evidence per acceptance criterion

### AC1: live GitHub Copilot Enhance prompt succeeds (verify skill, scratch server)
Setup:
- Scratch DB copy at `$S/sessions.db`, made with `sqlite3` backup and the lease cleared in the copy only.
- `bun run web:build` with Bun 1.4.4 produced no bundle drift (`git status` unchanged).
- Server started from `$S/ws` with `PBI_AGENT_SESSION_DB_PATH="$S/sessions.db" BROWSER=true nohup uv run --project <repo> pbi-agent web --port 7455 --no-open`.
- `GET /api/bootstrap` returned `provider "github_copilot"`, `profile_id "opus-5-5"`, `model "claude-opus-5.5"`. A non-`gpt-*` model routes to the Copilot Chat Completions path, which is the buggy one.

Request 1, default runtime with no session:
```text
POST http://127.0.0.1:7455/api/prompt/enhance
{"text":"fix teh grammer in readme and make it clear"}
-> HTTP 200 in 2.10s
{"text":"Correct the grammar and spelling errors in the README and revise unclear wording to improve readability.","session":null}
```

Request 2: a session was created with `POST /api/sessions {"profile_id":"opus-5-5"}` (session `1c5e9f39...`), then enhance was called with `session_id` so the tracer records the wire payload:
```text
-> HTTP 200 in 0.99s
{"text":"Fix the grammar and typos in the README and improve its clarity.", ...}
observability_events model_call: provider github_copilot, model claude-opus-5.5,
  url https://api.githubcopilot.com/chat/completions, status_code 200, success 1, error null
  request_payload keys: ['max_tokens', 'messages', 'model', 'stream']  (no tools / tool_choice / parallel_tool_calls)
  max_tokens 16384, stream false
```

Optional extra (plan step 5), ChatGPT/Codex. A session was created with `POST /api/sessions {"profile_id":"worker-pro"}` (provider `chatgpt`, model `gpt-6.2-astra`), then enhance was called with that `session_id`:
```text
-> HTTP 200 in 4.66s
{"text":"Correct grammatical errors in the README and clarify unclear passages.", ...}
model_call: url wss://chatgpt.com/backend-api/codex/responses, status 200, transport websocket
  request_payload keys: ['context_management', 'include', 'input', 'instructions', 'model', 'prompt_cache_key', 'reasoning', 'store', 'stream']
```
Codex accepts the slimmer tool-less body, so the plan's fallback of restoring `tools: []` is not needed.

I did not reproduce the 400 live before the fix (optional plan step 6). That would have meant reverting the source, which I avoided. The offline reproduction below and triage's reproduction cover the before state.

Shutdown:
- The recorded `web.pid` (397497) was the `cd && nohup` subshell, so killing it left `uv` (397499) and the server `python` (397507) running on 7455.
- I killed both by PID.
- Confirmed: `port 7455 free`, and `pgrep -af '[p]bi-agent web --port 7455'` finds no processes.

### AC2: no tool choice on tool-less requests; per-provider no-tools tests
Reproduce (bug_fix `reproduce`): I wrote the test first and ran it before touching `src/`:
```text
$ uv run pytest tests/test_github_copilot_provider.py::test_github_copilot_chat_completions_omits_tool_fields_without_tools
F
_____ test_github_copilot_chat_completions_omits_tool_fields_without_tools _____
tests/test_github_copilot_provider.py:521: in test_github_copilot_chat_completions_omits_tool_fields_without_tools
    assert "tools" not in body
E   AssertionError: assert 'tools' not in {'messages': [{'role': 'system', 'content': 'rewrite only'}, {'role': 'user', 'content': 'fix teh grammer'}], 'tools': [], 'tool_choice': 'auto', 'max_tokens': 16384, ...}
FAILED tests/test_github_copilot_provider.py::test_github_copilot_chat_completions_omits_tool_fields_without_tools
1 failed in 0.32s
```

All new tests before the fix (the 5 provider files, with the strengthened tool-using assertions already in place):
```text
FAILED tests/test_github_copilot_provider.py::test_github_copilot_chat_completions_omits_tool_fields_without_tools
FAILED tests/test_github_copilot_provider.py::test_github_copilot_responses_omits_tool_fields_without_tools
FAILED tests/test_openai_provider.py::test_openai_build_request_body_omits_tool_fields_without_tools[openai-api]
FAILED tests/test_openai_provider.py::test_openai_build_request_body_omits_tool_fields_without_tools[chatgpt-codex]
FAILED tests/test_xai_provider.py::test_xai_build_request_body_omits_tool_fields_without_tools
FAILED tests/test_google_provider.py::test_google_build_request_body_omits_tools_without_tools
FAILED tests/test_anthropic_provider.py::test_anthropic_request_body_omits_tools_without_tools
7 failed, 208 passed
```

After the fix, the provider test files below all pass (`327 passed`):
- `test_github_copilot_provider.py`, `test_openai_provider.py`, `test_xai_provider.py`, `test_google_provider.py`, `test_anthropic_provider.py`
- `test_openai_chatgpt_auth_provider.py`, `test_xai_auth_provider.py`, `test_generic_provider.py`, `test_google_gcp_provider.py`, `test_prompt_enhancement.py`

Tool-less wire shape from the `charz_gh455.py notools` dump, after the fix:
```text
openai (api)               tool fields {}  keys: context_management include input instructions max_output_tokens model prompt_cache_retention reasoning store stream
chatgpt/codex              tool fields {}  keys: context_management include input instructions model prompt_cache_key reasoning store stream
copilot responses (gpt-*)  tool fields {}  keys: include input instructions model reasoning stream
xai                        tool fields {}  keys: include input max_output_tokens model stream
google interactions        tool fields {}  keys: generation_config input model store stream system_instruction
anthropic                  tool fields {}  keys: cache_control max_tokens messages model output_config system thinking
copilot chat completions   tool fields {}  keys: max_tokens messages model stream
```
Before the fix, the same dump showed:
- Copilot chat: `{'tools': [], 'tool_choice': 'auto'}`
- Codex: `{'tools': [], 'tool_choice': 'auto', 'parallel_tool_calls': True}`
- OpenAI, Copilot Responses and xAI: `{'tools': [], 'parallel_tool_calls': True}`
- Google and Anthropic: `{'tools': []}`

Generic, Azure chat, GCP chat, GCP Responses, GCP Anthropic and generateContent already omitted these fields and are unchanged.

### AC3: tool-using requests unchanged
Byte-for-byte characterization:
- `charz_gh455.py` dumps the full `json.dumps(body)` with the default builtin tools for 7 builders:
  - OpenAI API, ChatGPT/Codex, Copilot Responses, xAI and Google through `_build_request_body`
  - Anthropic through `build_messages_body(provider._tools)`
  - Copilot chat through `request_turn` with a fake `urlopen`
- Tool counts: 7, 7, 8, 8, 8, 8, 8.
- Runs before the fix were deterministic: two runs had the same sha256.
```text
before sha256 1cfde406bf7168251a3050c4c0d76c71a1dea9df5dbcfe7372d8b1aff3de8118  charz_before.txt (41052 bytes)
after  sha256 1cfde406bf7168251a3050c4c0d76c71a1dea9df5dbcfe7372d8b1aff3de8118  charz_after.txt
$ diff charz_before.txt charz_after.txt && echo IDENTICAL
IDENTICAL
```

Existing tool-using assertions still pass:
- `test_openai_provider.py`: `parallel_tool_calls is True`, Codex `tool_choice == "auto"`, non-empty function tools
- `test_xai_provider.py`: `parallel_tool_calls`

New tool-using assertions (non-empty `tools`) were added for OpenAI API, xAI, Google and Anthropic.

### AC4: repo checks
```text
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 1 file would be reformatted, 1059 files already formatted
                                  (the file is .agents/factory/tasks/gh-455/triage.md: ruff formats its untracked
                                  python code block; not a code file and not owned by this stage, left as is)
uv run ruff format --check src tests -> 368 files already formatted
uv run basedpyright            -> 0 errors, 0 warnings, 0 notes
uv run pytest                  -> 2533 passed, 9 skipped in 72.49s (exit 0; the known flaky test did not fail)
bun run web:build              -> succeeded, no bundle drift (run only for the live check; no webapp change)
```

## Assumptions (provisional)
- No backend needs `tools: []` on a tool-less request. The live Codex and Copilot chat calls confirm this for those two. OpenAI API, xAI, Google Interactions, Anthropic and Copilot Responses were not called live. They rely on the generic and GCP precedent and on offline tests. If one of them turned out to require an empty `tools`, the fix would be to restore only `tools: []` there, still without a tool choice or `parallel_tool_calls`.
- Compaction uses the same `allowed_tools=()` + `ToolCatalog()` path, so it is fixed by the same change. It has no separate test; the provider tests cover the wire shape.
- Live check scope: I used the Copilot `claude-opus-5.5` profile (Chat Completions). The Copilot Responses path (`gpt-*` models) was not exercised live; no profile uses it.

## Think-ahead / follow-ups (not built)
- `ruff format --check .` flags python code blocks inside factory markdown stage files (here `triage.md`). Stage authors may want to use `text` fences for scripts, or the conductor could exclude `.agents/factory/` from the ruff format scope. Otherwise the repo-wide format check will show this finding on every task.
- The verify skill's scratch-server recipe records `$!` of a `cd ... && nohup ... &` group. That is the subshell PID, not the server, so `kill $(cat web.pid)` leaves `uv` and the server running. A fix would be to `exec` inside the group or record the PID of the port listener. This is a candidate memory or skill note.
- A reviewer can re-validate with:
  - `uv run python3 <scratch>/charz_gh455.py | sha256sum` (expect `1cfde406...`)
  - `uv run pytest tests/test_github_copilot_provider.py -k without_tools`

## Candidate memory notes (for main agent)
- Tool-less provider requests (enhance, compaction) must omit `tools` / tool choice / `parallel_tool_calls`; every builder now pops them when the tool list is empty (gh-455) [verified 2026-11-20].
- Verify-skill scratch server: `$!` after `cd X && nohup ... &` is the subshell; stop the server by port listener PID [verified 2026-11-20].

## Contradictions left
- None. No docs or guides make claims about tool fields on requests.
