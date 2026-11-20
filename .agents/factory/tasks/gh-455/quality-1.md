findings: 1

### Code Quality Findings

- `title: Reuse ChatCompletionsProtocol body builder in Copilot chat`
- `severity: major`
- `file:line: src/pbi_agent/providers/github_copilot_provider.py:362`
- `issue: The bug came from this subclass's forked copy of the chat body missing the generic tools guard; the patch patches the copy again instead of using the canonical owner, `self._protocol.build_request_body`.`
- `fix: Build the body with `self._protocol.build_request_body(instructions=instructions)`, set `body["stream"] = False`, and read headers from `body["messages"]`, deleting the duplicated dict and guard.`

### Overall Assessment

The change can land as is, but the Copilot chat body should go through the shared protocol builder so it cannot drift from it again.
