fix: done

# Fix round 1: gh-455 (source: quality-1.md)

## Findings fixed
1. **Reuse ChatCompletionsProtocol body builder in Copilot chat** (major, `src/pbi_agent/providers/github_copilot_provider.py`, `_GitHubCopilotChatCompletionsProvider._http_request`)
   - The duplicated body dict and the gh-455 `if not self._tools: pop(...)` guard are gone. The method now calls:
     ```python
     body = self._protocol.build_request_body(instructions=instructions)
     body["stream"] = False
     messages: list[dict[str, Any]] = body["messages"]
     ```
   - The image header and user-initiated header still read `messages`, which is now `body["messages"]`. The no-tools rule now comes from the shared builder's `if self.tools:` guard, so this path can no longer drift from it.

## Pre-edit field-by-field check (tool-using request)
| field | old Copilot body | shared `ChatCompletionsProtocol.build_request_body` |
| --- | --- | --- |
| messages | `[system(instructions)] + self._messages` | `[system(instructions)] + self.messages` (same list: `GenericProvider._messages` returns `self._protocol.messages`) |
| tools | `self._tools` | `self.tools` when non-empty (same list: `GenericProvider._tools` returns `self._protocol.tools`) |
| tool_choice | `"auto"` | `"auto"` when tools are non-empty |
| max_tokens | `self._settings.max_tokens` | `self.settings.max_tokens` (same object: `GenericProvider.__init__` and `set_runtime_settings` keep the two in sync) |
| model | set when `self._settings.model` | set when `self.settings.model` |
| stream | `False` | not set by the builder; Copilot still sets `False` after the call |
| other | none | none |

No field was added and no value changed. Only key order differs: tools and tool_choice now come after max_tokens, and stream comes last.

## Evidence (scratch: /tmp/claude-1000/-home-drod-workspace-pbi-agent/d9ece85a-34ce-4131-a7e4-9da1b38cf28d/scratchpad/)
- Before state: `charz_gh455.py` output before the edit was `fix1_charz_before.txt`. Its sha256 is `1cfde406...`, which matches build.md's `charz_after.txt`, so the baseline is the build state.
- `fix1_gh455.py` computes a sha256 for each builder section. For Copilot chat it also computes the sha256 of `json.dumps(body, sort_keys=True)`, and it hashes the request headers for a 2-turn run (user turn, then a tool-result plus steer follow-up), with tools and without. Outputs: `fix1_before.txt` and `fix1_after.txt`.
- Copilot chat, tool-using, sorted JSON is identical before and after:
  - turn 1: `f24815f1...d59d`
  - turn 2: `7f5da955...b4b6`
  - The raw sha changed (`5c81182e...` to `7b7918b2...`) only because of key order.
- Copilot chat, no tools, sorted JSON is identical before and after: turn 1 `f2cbc2df...`, turn 2 `85d4d325...`. Keys are still `[max_tokens, messages, model, stream]`.
- Copilot chat headers are identical before and after (`017bb4b8...`) for every turn.
- Raw sha256 of the other builders is unchanged before and after, for both the tool-using and no-tools runs:
  - openai `1ff912df...`, chatgpt/codex `6b0dfc8d...`, copilot responses `c6775102...`, xai `7e3e03f4...`, google `412f52fa...`, anthropic `de1fc788...`
  - The first 12 lines of each charz dump, which are every section except Copilot chat, are byte-identical (sha `f609b888...` with tools, `fee63e43...` without).

## Files changed
- `src/pbi_agent/providers/github_copilot_provider.py` (+3/-12)

## Validation
- `uv run ruff check .`: All checks passed!
- `uv run ruff format --check .`: 1063 files already formatted
- `uv run basedpyright`: 0 errors, 0 warnings, 0 notes
- `uv run pytest tests/test_github_copilot_provider.py tests/test_generic_provider.py tests/test_prompt_enhancement.py`: 49 passed, exit 0
  - This includes `test_github_copilot_chat_completions_omits_tool_fields_without_tools` and `test_github_copilot_responses_omits_tool_fields_without_tools`, both PASSED.
- I did not rerun the full suite or the live Copilot check. Only this one method changed, and the wire body has the same content apart from key order.

## Findings not fixed
- None.
