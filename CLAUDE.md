# Project Goal

Provide a local CLI foundation for a Power BI editing agent over the OpenAI Responses WebSocket API, with tool execution (including parallel tool calls) and report-template bootstrapping.

## Running Tests

```bash
uv run python -m unittest discover -s tests
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
