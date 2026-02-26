# AGENTS.md

## Project Goal

Provide a local CLI foundation for a Power BI editing agent over the OpenAI Responses WebSocket API, with tool execution (including parallel tool calls) and report-template bootstrapping.

## Running Tests

```bash
# No automated test suite is configured in this repository.
uv run pbi-agent --help
uv run pbi-agent tools list
uv run pbi-agent tools describe --name skill_knowledge
```

## Linting & Formatting

```bash
uvx ruff check . --fix && uvx ruff format .
```

## Project-Specific Tooling

```bash
uv run pbi-agent init --dest . --force
```

## Key Constraints

- Keep bundled PBIP template assets under `src/pbi_agent/report/`; packaging relies on `tool.hatch.build.targets.wheel.force-include`.
- Use `pbi-agent init` (command name is `init`, not `init-report`).
