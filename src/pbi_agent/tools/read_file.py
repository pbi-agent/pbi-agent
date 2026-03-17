from __future__ import annotations

import csv
import io
import math
from zipfile import BadZipFile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import DEFAULT_MAX_LINES
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import open_text_file
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

MAX_READ_FILE_OUTPUT_CHARS = 12_000
DATAFRAME_PREVIEW_ROWS = 3
MAX_TABULAR_SCHEMA_CHARS = 8_000
MAX_TABULAR_PREVIEW_CHARS = 2_500

_TABULAR_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".parquet",
    ".feather",
    ".ipc",
    ".arrow",
}

SPEC = ToolSpec(
    name="read_file",
    description=(
        "Read a workspace file safely, with line-range support for text files and "
        "compact summarization for tabular data such as CSV, TSV, and Excel, plus "
        "text extraction for DOCX files and text extraction and metadata for PDF "
        "files."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path relative to the workspace root "
                    "(or absolute within workspace)."
                ),
            },
            "start_line": {
                "type": "integer",
                "description": "1-based starting line number. Defaults to 1.",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return. Defaults to 200.",
            },
            "encoding": {
                "type": "string",
                "description": "Text encoding to use. Defaults to 'auto'.",
                "default": "auto",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    path_value = arguments.get("path", "")
    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}

    root = Path.cwd().resolve()
    start_line = normalize_positive_int(arguments.get("start_line"), default=1)
    max_lines = normalize_positive_int(
        arguments.get("max_lines"), default=DEFAULT_MAX_LINES
    )
    encoding = arguments.get("encoding", "auto")

    try:
        target_path = resolve_safe_path(root, path_value)
        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}
        if not target_path.is_file():
            return {"error": f"path is not a file: {target_path}"}

        suffix = target_path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            return _handle_excel_workbook(root, target_path)
        if suffix in _TABULAR_EXTENSIONS:
            return _handle_tabular_file(root, target_path, suffix)
        if suffix == ".docx":
            return _handle_docx_file(root, target_path)
        if suffix == ".pdf":
            return _handle_pdf_file(root, target_path)

        selected_lines: list[str] = []
        line_count = 0
        with open_text_file(target_path, encoding=str(encoding)) as text_handle:
            for line_count, line in enumerate(text_handle, start=1):
                if line_count < start_line:
                    continue
                if len(selected_lines) < max_lines:
                    selected_lines.append(line)

        selected = "".join(selected_lines)
        bounded_content, content_truncated = bound_output(
            selected, limit=MAX_READ_FILE_OUTPUT_CHARS
        )
        returned_start_line = start_line if selected_lines else 0
        returned_end_line = (
            returned_start_line + len(selected_lines) - 1 if selected_lines else 0
        )
        has_more_lines = returned_end_line < line_count if returned_end_line else False

        result: dict[str, Any] = {
            "path": relative_workspace_path(root, target_path),
            "start_line": returned_start_line,
            "end_line": returned_end_line,
            "total_lines": line_count,
            "content": bounded_content,
            "has_more_lines": has_more_lines,
        }
        if line_count == 0:
            result["empty"] = True
        if start_line > 1 or has_more_lines:
            result["windowed"] = True
        if content_truncated:
            result["content_truncated"] = True
        return result
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}


def _handle_tabular_file(root: Path, target_path: Path, suffix: str) -> dict[str, Any]:
    dataframe = _read_tabular_dataframe(target_path, suffix)
    result = _summarize_dataframe(dataframe)
    result["path"] = relative_workspace_path(root, target_path)
    return result


def _handle_excel_workbook(root: Path, target_path: Path) -> dict[str, Any]:
    workbook = _read_excel_workbook(target_path)
    sheets: list[dict[str, Any]] = []

    for sheet_name, dataframe in workbook.items():
        sheet_result = _summarize_dataframe(dataframe)
        sheet_result["name"] = sheet_name
        sheets.append(sheet_result)

    return {
        "path": relative_workspace_path(root, target_path),
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def _handle_docx_file(root: Path, target_path: Path) -> dict[str, Any]:
    full_text = _extract_docx_text(target_path)

    result: dict[str, Any] = {
        "path": relative_workspace_path(root, target_path),
        "content": full_text,
    }
    return result


def _extract_docx_text(path: Path) -> str:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = Document(str(path))
    except (BadZipFile, PackageNotFoundError) as exc:
        raise ValueError(
            f"unable to read docx file: {path.name} is unreadable or corrupt"
        ) from exc

    parts: list[str] = []

    for block in document.iter_inner_content():
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        if isinstance(block, Paragraph):
            parts.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                parts.append("\t".join(cell.text for cell in row.cells))

    for section in document.sections:
        for header_footer in (section.header, section.footer):
            if header_footer.is_linked_to_previous:
                continue
            for paragraph in header_footer.paragraphs:
                text = paragraph.text.strip()
                if text:
                    parts.append(text)

    return "\n".join(parts)


def _summarize_dataframe(dataframe: Any) -> dict[str, Any]:
    schema = dataframe.schema
    rows = dataframe.height
    columns = dataframe.width
    null_counts = {
        column_name: int(null_count)
        for column_name, null_count in zip(
            dataframe.columns, dataframe.null_count().row(0), strict=True
        )
    }
    kind_by_column = {
        column_name: _column_kind(dataframe, column_name, dtype)
        for column_name, dtype in schema.items()
    }

    schema_lines = [
        _summarize_tabular_column(
            dataframe,
            column_name,
            dtype,
            kind=kind_by_column[column_name],
            null_count=null_counts[column_name],
            row_count=rows,
        )
        for column_name, dtype in schema.items()
    ]
    schema_text, schema_truncated = bound_output(
        "\n".join(f"- {line}" for line in schema_lines),
        limit=MAX_TABULAR_SCHEMA_CHARS,
    )
    preview_text, preview_truncated = bound_output(
        _render_preview_csv(dataframe),
        limit=MAX_TABULAR_PREVIEW_CHARS,
    )

    result: dict[str, Any] = {
        "shape": {
            "rows": rows,
            "columns": columns,
        },
        "summary": _tabular_dataset_summary(
            rows=rows,
            columns=columns,
            kind_by_column=kind_by_column,
            null_counts=null_counts,
        ),
        "schema": schema_text,
        "preview": preview_text,
    }
    if schema_truncated:
        result["schema_truncated"] = True
    if preview_truncated:
        result["preview_truncated"] = True
    return result


def _read_tabular_dataframe(path: Path, suffix: str) -> Any:
    import polars as pl

    if suffix == ".csv":
        return _read_delimited_dataframe(path, separator=",")
    if suffix == ".tsv":
        return _read_delimited_dataframe(path, separator="\t")
    if suffix == ".parquet":
        return pl.read_parquet(path)
    if suffix in {".feather", ".ipc", ".arrow"}:
        return pl.read_ipc(path)
    raise ValueError(f"unsupported tabular file type: {suffix}")


def _read_excel_workbook(path: Path) -> dict[str, Any]:
    import polars as pl

    workbook = pl.read_excel(path, sheet_id=0, infer_schema_length=10_000)
    if isinstance(workbook, dict):
        return {
            sheet_name: _coerce_temporal_columns(dataframe)
            for sheet_name, dataframe in workbook.items()
        }
    return {"Sheet1": _coerce_temporal_columns(workbook)}


def _read_delimited_dataframe(path: Path, *, separator: str) -> Any:
    import polars as pl

    raw_bytes = path.read_bytes()
    if b"\r" in raw_bytes and b"\n" not in raw_bytes:
        raw_bytes = raw_bytes.replace(b"\r", b"\n")
        dataframe = pl.read_csv(
            io.BytesIO(raw_bytes),
            separator=separator,
            infer_schema_length=10_000,
        )
    else:
        dataframe = pl.read_csv(
            path,
            separator=separator,
            infer_schema_length=10_000,
        )
    return _coerce_temporal_columns(dataframe)


def _coerce_temporal_columns(dataframe: Any) -> Any:
    import polars as pl

    temporal_formats: tuple[tuple[Any, str], ...] = (
        (pl.Date, "%Y-%m-%d"),
        (pl.Date, "%m/%d/%Y"),
        (pl.Datetime, "%Y-%m-%d %H:%M:%S"),
        (pl.Datetime, "%Y-%m-%dT%H:%M:%S"),
    )
    expressions: list[Any] = []

    for column_name, dtype in dataframe.schema.items():
        if dtype != pl.String:
            continue

        series = dataframe[column_name]
        non_null = series.drop_nulls()
        if non_null.len() == 0:
            continue

        cleaned = series.str.strip_chars()
        for temporal_type, format_string in temporal_formats:
            parsed = cleaned.str.strptime(
                temporal_type,
                format=format_string,
                strict=False,
            )
            if parsed.drop_nulls().len() == non_null.len():
                expressions.append(parsed.alias(column_name))
                break

    if not expressions:
        return dataframe
    return dataframe.with_columns(expressions)


def _is_categorical_column(dataframe: Any, name: str, dtype: Any) -> bool:
    import polars as pl

    if dtype in {pl.Categorical, pl.Enum}:
        return True
    if dtype != pl.String or dataframe.height == 0:
        return False

    non_null = dataframe[name].drop_nulls()
    if non_null.len() == 0:
        return False
    unique_ratio = non_null.n_unique() / non_null.len()
    return unique_ratio <= 0.2 and non_null.n_unique() <= 100


def _column_kind(dataframe: Any, name: str, dtype: Any) -> str:
    import polars as pl

    if dtype.is_numeric():
        return "numeric"
    if dtype in {pl.Date, pl.Datetime, pl.Time}:
        return "datetime"
    if dtype == pl.Boolean:
        return "boolean"
    if _is_categorical_column(dataframe, name, dtype):
        return "categorical"
    if dtype in {pl.String, pl.Categorical, pl.Enum}:
        return "text"
    return "other"


def _tabular_dataset_summary(
    *,
    rows: int,
    columns: int,
    kind_by_column: dict[str, str],
    null_counts: dict[str, int],
) -> str:
    kind_order = ["numeric", "datetime", "categorical", "text", "boolean", "other"]
    kind_counts = {
        kind: sum(1 for value in kind_by_column.values() if value == kind)
        for kind in kind_order
    }
    mix_parts = [f"{count} {kind}" for kind, count in kind_counts.items() if count > 0]
    total_nulls = sum(null_counts.values())
    missing_summary = (
        "no missing values"
        if total_nulls == 0
        else f"{total_nulls} missing values across {sum(1 for count in null_counts.values() if count > 0)} columns"
    )

    parts = [f"{rows} rows x {columns} columns"]
    if mix_parts:
        parts.append("column mix: " + ", ".join(mix_parts))
    parts.append(f"missing values: {missing_summary}")
    return "; ".join(parts) + "."


def _summarize_tabular_column(
    dataframe: Any,
    column_name: str,
    dtype: Any,
    *,
    kind: str,
    null_count: int,
    row_count: int,
) -> str:
    series = dataframe[column_name]
    parts = [f"{column_name}: {dtype}"]
    if kind != "other":
        parts.append(f"kind={kind}")
    if null_count:
        null_ratio = (null_count / row_count) * 100 if row_count else 0.0
        parts.append(f"nulls={null_count} ({_format_number(null_ratio)}%)")

    non_null = series.drop_nulls()
    if non_null.len() == 0:
        parts.append("all values null")
        return "; ".join(parts)

    if kind == "numeric":
        parts.extend(
            [
                f"min={_format_scalar(non_null.min())}",
                f"max={_format_scalar(non_null.max())}",
                f"mean={_format_scalar(non_null.mean())}",
            ]
        )
        return "; ".join(parts)

    if kind == "datetime":
        parts.append(
            f"range={_format_scalar(non_null.min())}..{_format_scalar(non_null.max())}"
        )
        return "; ".join(parts)

    if kind == "boolean":
        parts.append(
            "values=" + ", ".join(_ordered_examples(non_null.to_list(), limit=2))
        )
        return "; ".join(parts)

    if kind == "categorical":
        distinct = non_null.n_unique()
        examples = _top_examples(non_null, limit=5)
        parts.append(f"distinct={distinct}")
        if examples:
            parts.append("examples=" + ", ".join(examples))
        return "; ".join(parts)

    if kind == "text":
        examples = _ordered_examples(non_null.to_list(), limit=3)
        if examples:
            parts.append("examples=" + ", ".join(examples))
        return "; ".join(parts)

    return "; ".join(parts)


def _render_preview_csv(dataframe: Any) -> str:
    preview = dataframe.head(DATAFRAME_PREVIEW_ROWS)
    if preview.height == 0:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=preview.columns,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in preview.to_dicts():
        writer.writerow(
            {
                column_name: _format_preview_value(row.get(column_name))
                for column_name in preview.columns
            }
        )
    return buffer.getvalue()


def _top_examples(series: Any, *, limit: int) -> list[str]:
    values = series.value_counts(sort=True)[series.name].to_list()
    return _ordered_examples(values, limit=limit)


def _ordered_examples(values: list[Any], *, limit: int) -> list[str]:
    examples: list[str] = []
    seen: set[str] = set()
    for value in values:
        rendered = _format_scalar(value)
        if rendered in seen:
            continue
        seen.add(rendered)
        examples.append(rendered)
        if len(examples) >= limit:
            break
    return examples


def _format_preview_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return str(value)
    return _format_scalar(value)


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_number(value)
    return str(value)


def _format_number(value: float) -> str:
    if math.isnan(value):
        return "null"
    if value.is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _handle_pdf_file(root: Path, target_path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(target_path))
    page_text = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(page_text)

    metadata: dict[str, Any] = {"pages": len(reader.pages)}
    if reader.metadata:
        if reader.metadata.title:
            metadata["title"] = reader.metadata.title
        if reader.metadata.author:
            metadata["author"] = reader.metadata.author

    result: dict[str, Any] = {
        "path": relative_workspace_path(root, target_path),
        "content": full_text,
        "metadata": metadata,
    }
    return result
