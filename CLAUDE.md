# Project Goal

Provide a local CLI foundation for a Power BI editing agent over the OpenAI Responses WebSocket API, with tool execution (including parallel tool calls) and report-template bootstrapping.

## Running Tests

```bash
uv run pytest
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only
uv run pytest -m slow
```

## Adding Tests

- Add new test modules under `tests/`.
- Name test files `test_*.py` so pytest discovers them automatically.
- Prefer pytest-style tests with plain `assert`; existing `unittest.TestCase` tests are still supported when needed.
- Import package code directly from `pbi_agent`; pytest is configured to add `src/` to `sys.path`, so new tests should not manually modify `sys.path`.
- Put shared fixtures in `tests/conftest.py` and use `@pytest.mark.parametrize(...)` for repeated input/output cases.
- Register any new custom markers in `pyproject.toml` under `tool.pytest.ini_options.markers` before using them.

Example:

```python
import pytest


@pytest.mark.parametrize(("value", "expected"), [("abc", 3), ("", 0)])
def test_string_length(value: str, expected: int) -> None:
    assert len(value) == expected
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
