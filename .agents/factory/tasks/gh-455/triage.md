## Summary
Confirmed offline: the GitHub Copilot Chat Completions path (any non-`gpt-*`/`o*` model, e.g. `claude-sonnet-4`) always sends `"tools": self._tools, "tool_choice": "auto"`. So a tool-less call (Enhance prompt, and also context compaction) sends `{"tools": [], "tool_choice": "auto"}`, which Copilot rejects with the reported 400. The only other backend that sends a tool choice with no tools is ChatGPT/Codex (`tool_choice: "auto"`). Several Responses-API backends also send `parallel_tool_calls: true` with `tools: []`. This is a small, contained fix in the provider request builders.

## Findings

### Enhance prompt call path
- `webapp/src/components/session/ComposerActions.tsx:196,346` (wand / Ctrl+Space) → `webapp/src/components/session/SessionPage.tsx:617` → `webapp/src/api.ts:1021` `POST /api/prompt/enhance`.
- `src/pbi_agent/web/api/routes/system.py:243-257` → `src/pbi_agent/web/session/saved_sessions.py:326` → `src/pbi_agent/web/session/prompt_enhancement.py:334` `enhance_prompt` → `_request_enhancement`.
- How "no tools" is passed: `prompt_enhancement.py:400-411` sets `settings.allowed_tools=()` and `tool_availability_overridden=True`, then passes `tool_catalog=ToolCatalog()` (an empty catalog) to `open_runtime_provider`. It then calls `provider.request_turn(...)` at `:414`. There is no explicit "no tools" flag. Each provider just ends up with `self._tools == []`.
- `src/pbi_agent/agent/session/runtime.py:1829-1841`: when a `tool_catalog` is given, `create_provider` is called directly and no MCP tools are added (MCP is only in the `else` branch). So the tool list really is empty.

### Request builders: what each sends when the tool list is empty

| Backend | Builder | `tools` | tool choice | `parallel_tool_calls` |
| --- | --- | --- | --- | --- |
| GitHub Copilot, Chat Completions (non-OpenAI models) | `src/pbi_agent/providers/github_copilot_provider.py:355-361` (`_http_request`) | `[]` always (`:357`) | **`"auto"` always (`:358`): bug** | not sent |
| GitHub Copilot, Responses (`gpt-*`, `o1/o3/o4`; routing at `github_copilot_backend.py:22-38`) | inherits `openai_provider.py:1184-1236`, override at `github_copilot_provider.py:199-219`; options at `:179-185` (no `tool_choice`) | `[]` | none | **`true`** |
| ChatGPT/Codex (`provider=chatgpt`, codex URL) | `openai_provider.py:1197-1210` with `chatgpt_codex_backend.py:276-286` | `[]` | **`"auto"` (`chatgpt_codex_backend.py:284` → `openai_provider.py:1209-1210`)** | **`true`** |
| OpenAI API (Responses) | `openai_provider.py:1194-1210`; null backend options `chatgpt_codex_backend.py:176-177` (`tool_choice=None`) | `[]` (`:1197`) | none | **`true` (`:1198`)** |
| xAI (Responses) | `src/pbi_agent/providers/xai_provider.py:327-334` | `[]` (`:331`) | none | **`true` (`:332`)** |
| Google Gemini (Interactions) | `src/pbi_agent/providers/google_provider.py:296-313` | `[]` (`:299`) | none (no `tool_config` anywhere) | n/a |
| Anthropic (Messages, also Azure Anthropic) | `src/pbi_agent/providers/protocols/anthropic_messages.py:45-71`, called from `anthropic_provider.py:265-270` | `[]` (`anthropic_messages.py:57`) | none (`tool_choice` never set) | n/a |
| Generic OpenAI-compatible (also Azure chat, GCP chat shape) | `src/pbi_agent/providers/protocols/chat_completions.py:132-144` | omitted when empty (`:139-141`) | only with tools | n/a |
| Google GCP Responses shape | `src/pbi_agent/providers/google_gcp_provider.py:1077-1103` | omitted when empty (`:1100-1102`) | none | only with tools |
| Google GCP Anthropic shape | `google_gcp_provider.py:1455-1466` | omitted when empty (`:1462-1463`) | none | n/a |
| Google GCP / Gemini generateContent | `src/pbi_agent/providers/protocols/gemini_generate_content.py:127-136` | omitted when empty (`:134-135`) | none (no `toolConfig`) | n/a |

- `git log` shows `79a5a6bb Omit empty chat completion tools`. That commit fixed the shared `ChatCompletionsProtocol` but not Copilot's own copy of the body. Copilot's `_GitHubCopilotChatCompletionsProvider` subclasses `GenericProvider` but overrides `_http_request` with its own body (`github_copilot_provider.py:342-361`), so the fix never reached it.
- `src/pbi_agent/providers/protocols/openai_responses.py` and `google_interactions.py` do not build tool fields. They are not involved.

### Other tool-less calls
- Context compaction: `src/pbi_agent/agent/session/compaction.py:48-58` uses the same pattern (`allowed_tools=()`, `ToolCatalog()`). It hits the same Copilot 400 (inferred from identical code path). It is fixed by the same provider change.
- Session titles: `src/pbi_agent/session_titles.py:167` uses a local llama.cpp process, not a provider. Not affected.

### `parallel_tool_calls` without tools
- OpenAI Chat Completions documents and enforces "`parallel_tool_calls` is only allowed when `tools` are specified" (inferred from upstream API behaviour, not tested here). Our Chat Completions paths (generic, Copilot chat) do not send it, so they are fine.
- Responses API backends (OpenAI, ChatGPT/Codex, Copilot Responses, xAI) send `parallel_tool_calls: true` with `tools: []`. No user report of a failure. OpenAI Responses is believed to accept it (inferred). It is unverified for the Copilot Responses proxy and for xAI. The GCP Responses shape already guards it (`google_gcp_provider.py:1100-1102`), which is a precedent for omitting it when there are no tools.

## Reproduction
Offline, no network. `urllib.request.urlopen` is monkeypatched to capture the body.

Script: `/tmp/claude-1000/-home-drod-workspace-pbi-agent/d9ece85a-34ce-4131-a7e4-9da1b38cf28d/scratchpad/repro_gh455.py`

```python
import json, urllib.request
from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL
from pbi_agent.config import DEFAULT_MAX_TOKENS, Settings
from pbi_agent.models.messages import TokenUsage, UserTurnInput
from pbi_agent.providers.github_copilot_provider import GitHubCopilotProvider
from pbi_agent.tools.catalog import ToolCatalog

seen = {}


class R:
    headers = {}

    def read(self):
        return json.dumps(
            {
                "id": "x",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }
        ).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout):
    seen["body"] = json.loads(req.data.decode())
    return R()


urllib.request.urlopen = fake_urlopen


class D:
    def __getattr__(self, n):
        return lambda *a, **k: None


settings = Settings(
    api_key="",
    auth=OAuthSessionAuth(
        provider_id="c",
        backend="github_copilot",
        access_token="gho_x",
        refresh_token=None,
        plan_type="github_copilot",
    ),
    provider="github_copilot",
    responses_url=GITHUB_COPILOT_RESPONSES_URL,
    model="claude-sonnet-4",
    max_tokens=DEFAULT_MAX_TOKENS,
    allowed_tools=(),
)
p = GitHubCopilotProvider(
    settings, system_prompt="rewrite only", tool_catalog=ToolCatalog()
)
p.request_turn(
    user_input=UserTurnInput(text="fix grammar"),
    display=D(),
    session_usage=TokenUsage(),
    turn_usage=TokenUsage(),
)
b = seen["body"]
print({k: b[k] for k in ("tools", "tool_choice") if k in b})
```

Command and output:
```
$ uv run python3 .../scratchpad/repro_gh455.py
{'tools': [], 'tool_choice': 'auto'}
```

A cross-backend dump (`.../scratchpad/bodies_gh455.py`) calls each `_build_request_body` with an empty `ToolCatalog()` and `allowed_tools=()`:
```
openai (api)                 {'tools': [], 'parallel_tool_calls': True}
chatgpt/codex                {'tools': [], 'tool_choice': 'auto', 'parallel_tool_calls': True}
copilot responses (gpt-*)    {'tools': [], 'parallel_tool_calls': True}
xai                          {'tools': [], 'parallel_tool_calls': True}
google interactions          {'tools': []}
anthropic                    {'tools': []}
```

Failing-test outline for the regression test, to go in `tests/test_github_copilot_provider.py`: copy `test_github_copilot_non_openai_model_uses_chat_completions` (`:409`), build `GitHubCopilotProvider(_make_settings(model="claude-sonnet-4"), system_prompt="rewrite only", tool_catalog=ToolCatalog())`, and assert `"tools" not in body and "tool_choice" not in body`. Today this fails with `tool_choice == "auto"`. Model it on `tests/test_generic_provider.py:70` `test_generic_request_turn_omits_empty_tools`.

## Existing test coverage of request shapes
- Copilot: `tests/test_github_copilot_provider.py`. Chat body at `:409-470`, Responses body at `:163-228`. No no-tools test.
- OpenAI and ChatGPT/Codex: `tests/test_openai_provider.py` (`:280`, `:310-311` assert `parallel_tool_calls`/`tool_choice == "auto"` with tools; `:380`) and `tests/test_openai_chatgpt_auth_provider.py`. No no-tools test.
- xAI: `tests/test_xai_provider.py:190` (`parallel_tool_calls`), plus `tests/test_xai_auth_provider.py`. No no-tools test.
- Google Interactions: `tests/test_google_provider.py`. No no-tools test.
- Anthropic: `tests/test_anthropic_provider.py`. No no-tools test.
- Generic: `tests/test_generic_provider.py:70` already covers no tools; `:757,785,865` cover the tools path.
- Google GCP: `tests/test_google_gcp_provider.py`. Many tests already use `ToolCatalog()` (`:483`, `:538`, …); `:1858-1870` covers tools plus `parallel_tool_calls`.
- Enhance prompt service: `tests/test_prompt_enhancement.py:127` (`..._without_tools_and_records_usage`). It uses a fake provider, so it does not check the wire shape.

## Unknowns
- Should `tools: []` and `parallel_tool_calls: true` also be dropped when there are no tools on the Responses backends (OpenAI, ChatGPT/Codex, Copilot Responses, xAI), and should the empty `tools` key be dropped for Google Interactions and Anthropic? The acceptance criteria require only "no tool choice". Omitting all tool fields when empty is the conservative, consistent option and matches the existing GCP and generic guards. The planner can decide this; it is not blocking.
- Does the Copilot Responses proxy reject `parallel_tool_calls` or `tools: []` without tools? Not verifiable offline. The live check covers only the model the user picks. The planner should guard it anyway (inferred low-risk).
- Does the ChatGPT/Codex backend need `tool_choice` on every request? Dropping it only when `tools` is empty keeps tool-using turns unchanged (AC3).
- Dirty tree: only `TODO.md` and the untracked factory task dir. No overlap with the code in scope.
- AC1 (live Copilot check) needs a human with a Copilot account at verify time. This does not block planning.

## Scope estimate
- Surfaces: python (providers plus provider tests). No frontend, API contract or docs changes.
- Likely files or areas: `src/pbi_agent/providers/github_copilot_provider.py`, `src/pbi_agent/providers/openai_provider.py` (`_build_request_body`; covers OpenAI, ChatGPT/Codex and Copilot Responses), `src/pbi_agent/providers/xai_provider.py`, and optionally `google_provider.py` and `protocols/anthropic_messages.py`. Tests: `tests/test_github_copilot_provider.py`, `tests/test_openai_provider.py` (or `test_openai_chatgpt_auth_provider.py`), `tests/test_xai_provider.py`, and optionally `tests/test_google_provider.py` and `tests/test_anthropic_provider.py`.
- Size: about 3-5 source files with 10-30 lines changed, plus 3-5 test files with 80-200 lines added. Well under 15 files and 500 lines.

## Risk and profile
- risk: high. Trigger: provider request paths (`src/pbi_agent/providers/`). The diff-size trigger is not hit.
- profile: keep `bug_fix`. This is existing behaviour that is wrong against the intended "no tools means no tool choice" rule (the generic path already follows it). No new capability.

## Verdict
triage: proceed. Bug reproduced offline (Copilot chat body `{'tools': [], 'tool_choice': 'auto'}`). The fix is confined to the provider body builders, and the planner can settle every remaining unknown.
