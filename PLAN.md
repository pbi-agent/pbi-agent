# Plan: Provider-Aware Tool Availability

## Summary
Centralize provider tool-availability policy so the model only sees the editing and web tools appropriate for the active backend. OpenAI official Responses API and the ChatGPT Codex backend use V4A `apply_patch`; other providers use the simpler file edit tools. `read_web_url` follows the existing `web_search` runtime flag.

## Checklist
- [X] Add a small shared tool-policy helper, e.g. `pbi_agent.tools.availability.effective_excluded_tool_names(settings, excluded_names)`, that merges session exclusions with backend policy.
- [X] Apply the helper in every provider `refresh_tools()` before provider-specific tool serialization/native web-search appending: OpenAI, xAI, Google, Anthropic, Generic, and GitHub Copilot delegates.
- [X] For `settings.provider in {"openai", "chatgpt"}`, advertise `apply_patch` and hide `replace_in_file`/`write_file`; this covers both OpenAI official API and ChatGPT Codex because both flow through `OpenAIProvider`/`ChatGPTCodexBackend`.
- [X] For all other providers/backends, hide `apply_patch` and keep `replace_in_file`/`write_file` available.
- [X] Hide `read_web_url` whenever `settings.web_search` is false; keep native provider search tools controlled by the existing `if settings.web_search` branches.
- [X] Keep the built-in registry and tool handlers unchanged so direct tool tests, display formatting, and MCP catalog merging still work; only provider-advertised tool definitions change.
- [X] Ensure `Provider.set_excluded_tools()` continues to work by storing session-only exclusions while each `refresh_tools()` recomputes policy exclusions, so toggling `ask_user`/`sub_agent` cannot re-enable hidden tools.
- [X] Update stale inline/docs wording that says all providers receive `apply_patch` or that `read_web_url` is always available.

## Public Interfaces / Behavior Changes
- No CLI flags, config schema, web API, or persisted data changes.
- Provider tool lists change:
  - OpenAI/chatgpt: `apply_patch` yes; `replace_in_file`/`write_file` no.
  - Non-OpenAI providers, including Azure, generic OpenAI-compatible, GitHub Copilot, xAI, Google, and Anthropic: `apply_patch` no; `replace_in_file`/`write_file` yes.
  - All providers: `read_web_url` only when `settings.web_search` is true.
- MCP tools and native web-search result parsing/display behavior are unchanged.

## Test Plan
- [X] Add focused tests for the shared policy helper covering OpenAI/chatgpt, non-OpenAI providers, existing caller exclusions, and `web_search=False`.
- [X] Add/adjust provider tests to inspect serialized tool names for OpenAI official API and ChatGPT Codex backend: `apply_patch` present, `replace_in_file`/`write_file` absent, and `read_web_url` gated by `web_search`.
- [X] Add/adjust provider tests for representative non-OpenAI formats (Anthropic, Google, xAI, Generic, GitHub Copilot) to assert `apply_patch` absent, file edit tools present, and `read_web_url` gated.
- [X] Add a regression test that `set_excluded_tools({"ask_user"})` preserves policy exclusions after refresh.
- [X] Validate with `uv run pytest -q --tb=short -x tests/test_tool_registry.py tests/test_openai_provider.py tests/test_generic_provider.py tests/test_anthropic_provider.py tests/test_google_provider.py tests/test_xai_provider.py tests/test_github_copilot_provider.py tests/test_provider_factory.py`. Passed.
- [X] Run Python quality checks: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run basedpyright`. Passed.
- [!] Final full-suite check `uv run pytest -q --tb=short -x` stopped at unrelated existing sandbox expectation `tests/cli/test_sandbox.py::DefaultWebCommandTests::test_sandbox_dockerfile_uses_alpine_with_minimal_apk_packages` expecting the pre-Rust minimal APK list.
- [-] If docs are edited, run `bun run docs:build`. Skipped; no docs edited.

## Assumptions / Scope
- “OpenAI model/backend” means repo provider kinds `openai` and `chatgpt`; `gpt-*` model names served by Azure, Generic, GitHub Copilot, or other providers remain non-OpenAI for this policy.
- “Available” means advertised in provider tool definitions sent to the model. The registry and handlers remain registered for direct execution/tests and existing runtime fallback behavior.
- No backward-compatibility shims or migrations are needed.
