from __future__ import annotations


class FrontmatterParseError(ValueError):
    """Raised when limited YAML frontmatter cannot be parsed safely."""


def parse_simple_frontmatter(
    frontmatter: str,
    *,
    block_scalar_keys: frozenset[str] | None = None,
    include_keys: frozenset[str] | None = None,
) -> dict[str, str]:
    """Parse a limited YAML frontmatter subset.

    Supported syntax:
    - ``key: value`` scalar pairs
    - blank lines and ``#`` comments
    - ``|`` and ``>`` block scalars with indented content for allowed keys

    This is intentionally not a general YAML parser. Unsupported YAML constructs
    such as lists, nested mappings, and anchors are rejected.
    """

    result: dict[str, str] = {}
    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(line) - len(line.lstrip(" "))
        colon_idx = stripped.find(":")
        if colon_idx < 0:
            raise FrontmatterParseError(
                f"frontmatter line is not a key-value pair: {stripped!r}."
            )

        key = stripped[:colon_idx].strip()
        value = stripped[colon_idx + 1 :].strip()
        if not key:
            raise FrontmatterParseError("frontmatter contains an empty key.")

        should_capture = include_keys is None or key in include_keys

        if not value:
            skipped_ignored_nested_block = False
            next_index = index + 1
            while next_index < len(lines):
                next_line = lines[next_index]
                next_stripped = next_line.strip()
                if not next_stripped or next_stripped.startswith("#"):
                    next_index += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_indent > indent:
                    if should_capture:
                        raise FrontmatterParseError(
                            f"unsupported YAML structure for key {key!r}; only scalar "
                            "values and block scalars are supported."
                        )
                    index = _skip_nested_block(
                        lines,
                        start_index=next_index,
                        parent_indent=indent,
                    )
                    skipped_ignored_nested_block = True
                    break
                if (
                    not should_capture
                    and next_indent == indent
                    and _is_indentless_sequence_entry(next_stripped)
                ):
                    index = _skip_indentless_sequence_block(
                        lines,
                        start_index=next_index,
                        parent_indent=indent,
                    )
                    skipped_ignored_nested_block = True
                    break
                break
            if skipped_ignored_nested_block:
                continue

        block_scalar_style = _parse_block_scalar_style(value)
        if block_scalar_style is not None:
            if (
                should_capture
                and block_scalar_keys is not None
                and key not in block_scalar_keys
            ):
                allowed = ", ".join(repr(item) for item in sorted(block_scalar_keys))
                raise FrontmatterParseError(
                    f"unsupported block scalar for key {key!r}; only {allowed} may "
                    "use block scalars."
                )
            block_lines, index = _parse_block_scalar_lines(
                lines,
                start_index=index + 1,
                parent_indent=indent,
            )
            if should_capture:
                if block_scalar_style == "|":
                    result[key] = "\n".join(block_lines)
                else:
                    result[key] = " ".join(
                        part.strip() for part in block_lines if part.strip()
                    )
            continue

        if should_capture:
            result[key] = _parse_scalar(value)
        index += 1

    if not result:
        raise FrontmatterParseError("frontmatter is empty.")
    return result


def _parse_scalar(value: str) -> str:
    if len(value) >= 2 and value[:1] == value[-1:] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_block_scalar_style(value: str) -> str | None:
    if value in {"|", ">", "|-", ">-", "|+", ">+"}:
        return value[0]
    return None


def _parse_block_scalar_lines(
    lines: list[str],
    *,
    start_index: int,
    parent_indent: int,
) -> tuple[list[str], int]:
    block_lines: list[str] = []
    block_indent: int | None = None
    index = start_index
    while index < len(lines):
        next_line = lines[index]
        next_stripped = next_line.strip()
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if not next_stripped:
            block_lines.append("")
            index += 1
            continue
        if next_indent <= parent_indent:
            break
        if block_indent is None:
            block_indent = next_indent
        if next_indent < block_indent:
            break
        block_lines.append(next_line[block_indent:])
        index += 1
    return block_lines, index


def _skip_nested_block(
    lines: list[str],
    *,
    start_index: int,
    parent_indent: int,
) -> int:
    index = start_index
    while index < len(lines):
        next_line = lines[index]
        next_stripped = next_line.strip()
        if not next_stripped or next_stripped.startswith("#"):
            index += 1
            continue
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if next_indent <= parent_indent:
            break
        index += 1
    return index


def _skip_indentless_sequence_block(
    lines: list[str],
    *,
    start_index: int,
    parent_indent: int,
) -> int:
    index = start_index
    while index < len(lines):
        next_line = lines[index]
        next_stripped = next_line.strip()
        if not next_stripped or next_stripped.startswith("#"):
            index += 1
            continue
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if next_indent < parent_indent:
            break
        if next_indent == parent_indent and not _is_indentless_sequence_entry(
            next_stripped
        ):
            break
        index += 1
    return index


def _is_indentless_sequence_entry(stripped: str) -> bool:
    return stripped == "-" or stripped.startswith("- ")
