# Python Extensions

Project-local Python extensions live in `.agents/extensions/*.py`. Each file
defines one action that appears as both:

- a slash command in the web composer, such as `/summarize-csv`
- a model-callable tool with the same normalized name, without the leading `/`

Extensions are trusted local code. pbi-agent runs them in a subprocess with a
per-extension virtual environment, but this is isolation for dependency hygiene,
not a security sandbox.

## Script metadata

Extensions use PEP 723 script metadata. The `[tool.pbi-agent.extension]` table
requires `name`, `description`, and `input_schema`.

```python
# /// script
# dependencies = ["pandas==3.0.1"]
#
# [tool.pbi-agent.extension]
# name = "summarize-csv"
# description = "Summarize a CSV file"
# input_schema = { type = "object", properties = { path = { type = "string" } }, required = ["path"], additionalProperties = false }
# ///


def run(input: dict) -> dict:
    import pandas as pd

    frame = pd.read_csv(input["path"])
    return {"rows": len(frame), "columns": list(frame.columns)}
```

The `name` is normalized with the same slug rules as project commands. Invalid
metadata, duplicate names, and names that collide with existing commands or
tools are skipped and reported by `/extensions`.

## Running extensions

The extension contract is:

```python
def run(input: dict) -> dict: ...
```

Manual slash invocation passes the text after the command:

```text
/summarize-csv data/sales.csv
```

becomes:

```json
{ "text": "data/sales.csv" }
```

When the model calls the extension as a tool, pbi-agent passes the JSON object
the model supplied according to `input_schema`.

## Dependencies and cache

On first use, pbi-agent creates a uv-managed environment under:

```text
~/.pbi-agent/extensions/<workspace-key>/<extension-name>/
```

It runs `uv venv` and installs metadata dependencies with `uv pip install`.
Changing dependencies or extension metadata updates the environment on the next
run. Use `/reload` after editing extension files so active sessions refresh tool
definitions.