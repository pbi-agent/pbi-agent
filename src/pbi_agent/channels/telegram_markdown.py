from __future__ import annotations

from typing import Any

TELEGRAM_MESSAGE_LIMIT_UTF16 = 4096


def split_telegram_text(text: str) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    current = ""
    current_units = 0
    for char in text:
        units = len(char.encode("utf-16-le")) // 2
        if current and current_units + units > TELEGRAM_MESSAGE_LIMIT_UTF16:
            chunks.append(current)
            current = char
            current_units = units
        else:
            current += char
            current_units += units
    if current:
        chunks.append(current)
    return chunks


def format_telegram_markdown_chunks(
    text: str,
) -> list[tuple[str, list[dict[str, Any]]]]:
    plain_text, entities = markdown_to_telegram_entities(text)
    return _split_telegram_entities(plain_text, entities)


def markdown_to_telegram_entities(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Convert common assistant Markdown into Telegram Bot API message entities."""
    output: list[str] = []
    entities: list[dict[str, Any]] = []
    lines = text.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                closing = lines[index]
                trailing_newline = "\n" if closing.endswith("\n") else ""
                index += 1
            else:
                trailing_newline = ""
            start = _utf16_len("".join(output))
            code = "".join(code_lines)
            output.append(code)
            _add_entity(
                entities,
                "pre",
                start,
                _utf16_len(code.rstrip()),
                language=language or None,
            )
            if trailing_newline:
                output.append(trailing_newline)
            continue
        heading_marker = _heading_marker(line)
        if heading_marker is not None:
            content = line[heading_marker:]
            start = _utf16_len("".join(output))
            parsed, parsed_entities = _parse_inline_markdown(content, start)
            output.append(parsed)
            entities.extend(parsed_entities)
            _add_formatting_entity_excluding_code_pre(
                entities, "bold", start, _utf16_len(parsed.rstrip()), parsed
            )
            index += 1
            continue
        start = _utf16_len("".join(output))
        parsed, parsed_entities = _parse_inline_markdown(line, start)
        output.append(parsed)
        entities.extend(parsed_entities)
        index += 1
    return "".join(output), entities


def _parse_inline_markdown(
    text: str,
    base_offset: int,
) -> tuple[str, list[dict[str, Any]]]:
    output: list[str] = []
    entities: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        if text[index] == "\\" and _should_consume_markdown_escape(text, index):
            output.append(text[index + 1])
            index += 2
            continue
        if text[index] == "`":
            end = text.find("`", index + 1)
            if end > index + 1:
                start = base_offset + _utf16_len("".join(output))
                value = text[index + 1 : end]
                output.append(value)
                _add_entity(entities, "code", start, _utf16_len(value.rstrip()))
                index = end + 1
                continue
        link = _parse_markdown_link(text, index)
        if link is not None:
            label, url, next_index = link
            start = base_offset + _utf16_len("".join(output))
            parsed_label, label_entities = _parse_inline_markdown(label, start)
            output.append(parsed_label)
            label_length = _utf16_len(parsed_label.rstrip())
            if any(entity.get("type") in {"code", "pre"} for entity in label_entities):
                entities.extend(
                    entity
                    for entity in label_entities
                    if entity.get("type") not in {"code", "pre"}
                )
            else:
                entities.extend(label_entities)
            _add_entity(
                entities,
                "text_link",
                start,
                label_length,
                url=url,
            )
            index = next_index
            continue
        marker = None
        entity_type = ""
        for candidate, candidate_type in (
            ("**", "bold"),
            ("__", "bold"),
            ("~~", "strikethrough"),
            ("*", "italic"),
            ("_", "italic"),
        ):
            if text.startswith(candidate, index):
                marker = candidate
                entity_type = candidate_type
                break
        if marker is not None and (
            marker != "_" or _can_start_underscore_entity(text, index)
        ):
            end = _find_closing_marker(text, marker, index + len(marker))
            if end > index + len(marker):
                start = base_offset + _utf16_len("".join(output))
                inner = text[index + len(marker) : end]
                parsed_inner, inner_entities = _parse_inline_markdown(inner, start)
                output.append(parsed_inner)
                entities.extend(inner_entities)
                _add_formatting_entity_excluding_code_pre(
                    entities,
                    entity_type,
                    start,
                    _utf16_len(parsed_inner.rstrip()),
                    parsed_inner,
                )
                index = end + len(marker)
                continue
        output.append(text[index])
        index += 1
    return "".join(output), entities


def _should_consume_markdown_escape(text: str, index: int) -> bool:
    if index + 1 >= len(text):
        return False
    escaped = text[index + 1]
    if escaped == "`":
        return _marker_escape_prevents_markdown(text, index, "`")
    if escaped == "*":
        marker = "**" if text.startswith("**", index + 1) else "*"
        return _marker_escape_prevents_markdown(text, index, marker)
    if escaped == "_":
        marker = "__" if text.startswith("__", index + 1) else "_"
        return _marker_escape_prevents_markdown(text, index, marker)
    if escaped == "~":
        return text.startswith("~~", index + 1) and _marker_escape_prevents_markdown(
            text, index, "~~"
        )
    if escaped == "[":
        return _parse_markdown_link(text, index + 1) is not None
    return False


def _marker_escape_prevents_markdown(text: str, index: int, marker: str) -> bool:
    marker_index = index + 1
    if not text.startswith(marker, marker_index):
        return False
    if marker == "`":
        if text.find("`", marker_index + len(marker)) > marker_index:
            return True
    elif (marker != "_" or _can_start_underscore_entity(text, marker_index)) and (
        _find_closing_marker(text, marker, marker_index + len(marker)) > marker_index
    ):
        return True
    prior_escape = text.rfind("\\" + marker, 0, index)
    if prior_escape < 0:
        return False
    if marker == "`":
        return text.find("`", prior_escape + 1 + len(marker)) == marker_index
    return (
        _find_closing_marker(text, marker, prior_escape + 1 + len(marker))
        == marker_index
    )


def _parse_markdown_link(text: str, index: int) -> tuple[str, str, int] | None:
    if index >= len(text) or text[index] != "[":
        return None
    label_end = text.find("]", index + 1)
    if (
        label_end <= index + 1
        or label_end + 1 >= len(text)
        or text[label_end + 1] != "("
    ):
        return None
    url_end = text.find(")", label_end + 2)
    if url_end <= label_end + 2:
        return None
    url = text[label_end + 2 : url_end].strip()
    if not url:
        return None
    return text[index + 1 : label_end], url, url_end + 1


def _find_closing_marker(text: str, marker: str, start: int) -> int:
    index = start
    while True:
        index = text.find(marker, index)
        if index < 0:
            return -1
        if marker != "_" or _can_end_underscore_entity(text, index):
            return index
        index += len(marker)


def _heading_marker(line: str) -> int | None:
    stripped = line.lstrip()
    leading = len(line) - len(stripped)
    count = 0
    while count < len(stripped) and stripped[count] == "#":
        count += 1
    if 1 <= count <= 6 and count < len(stripped) and stripped[count] == " ":
        return leading + count + 1
    return None


def _can_start_underscore_entity(text: str, index: int) -> bool:
    previous = text[index - 1] if index > 0 else " "
    following = text[index + 1] if index + 1 < len(text) else " "
    return not (previous.isalnum() and following.isalnum())


def _can_end_underscore_entity(text: str, index: int) -> bool:
    previous = text[index - 1] if index > 0 else " "
    following = text[index + 1] if index + 1 < len(text) else " "
    return not (previous.isalnum() and following.isalnum())


def _add_formatting_entity_excluding_code_pre(
    entities: list[dict[str, Any]],
    entity_type: str,
    offset: int,
    length: int,
    text: str,
) -> None:
    """Add a formatting entity, split around code/pre entities Telegram forbids."""
    if length <= 0:
        return
    end = offset + length
    blockers = sorted(
        (
            (int(entity["offset"]), int(entity["offset"]) + int(entity["length"]))
            for entity in entities
            if entity.get("type") in {"code", "pre"}
            and int(entity["offset"]) < end
            and int(entity["offset"]) + int(entity["length"]) > offset
        ),
        key=lambda blocker: blocker[0],
    )
    current = offset
    for blocker_start, blocker_end in blockers:
        segment_end = min(max(blocker_start, offset), end)
        segment_length = _trim_entity_trailing_whitespace(
            text,
            current - offset,
            segment_end - current,
        )
        _add_entity(entities, entity_type, current, segment_length)
        current = max(current, min(blocker_end, end))
    segment_length = _trim_entity_trailing_whitespace(
        text,
        current - offset,
        end - current,
    )
    _add_entity(entities, entity_type, current, segment_length)


def _trim_entity_trailing_whitespace(text: str, offset: int, length: int) -> int:
    if length <= 0:
        return length
    entity_end = offset + length
    current_offset = 0
    trimmed_length = 0
    for char in text:
        char_start = current_offset
        char_end = char_start + _utf16_len(char)
        current_offset = char_end
        if char_start < offset:
            continue
        if char_end > entity_end:
            break
        if not char.isspace():
            trimmed_length = char_end - offset
    return trimmed_length


def _add_entity(
    entities: list[dict[str, Any]],
    entity_type: str,
    offset: int,
    length: int,
    *,
    url: str | None = None,
    language: str | None = None,
) -> None:
    if length <= 0:
        return
    entity: dict[str, Any] = {"type": entity_type, "offset": offset, "length": length}
    if url is not None:
        entity["url"] = url
    if language is not None:
        entity["language"] = language
    entities.append(entity)


def _split_telegram_entities(
    text: str,
    entities: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    chunks: list[tuple[str, int, int]] = []
    current = ""
    chunk_start = 0
    current_units = 0
    for char in text:
        units = _utf16_len(char)
        if current and current_units + units > TELEGRAM_MESSAGE_LIMIT_UTF16:
            chunks.append((current, chunk_start, chunk_start + current_units))
            chunk_start += current_units
            current = char
            current_units = units
        else:
            current += char
            current_units += units
    if current:
        chunks.append((current, chunk_start, chunk_start + current_units))
    formatted: list[tuple[str, list[dict[str, Any]]]] = []
    for chunk_text, chunk_start, chunk_end in chunks:
        chunk_entities: list[dict[str, Any]] = []
        for entity in entities:
            entity_start = int(entity["offset"])
            entity_end = entity_start + int(entity["length"])
            overlap_start = max(entity_start, chunk_start)
            overlap_end = min(entity_end, chunk_end)
            if overlap_end <= overlap_start:
                continue
            chunk_entity = dict(entity)
            chunk_entity["offset"] = overlap_start - chunk_start
            chunk_entity["length"] = _trim_chunk_entity_length(
                chunk_text,
                chunk_entity["offset"],
                overlap_end - overlap_start,
                trim_trailing=entity_end > chunk_end,
            )
            if chunk_entity["length"] <= 0:
                continue
            chunk_entities.append(chunk_entity)
        formatted.append((chunk_text, chunk_entities))
    return formatted


def _trim_chunk_entity_length(
    chunk_text: str,
    offset: int,
    length: int,
    *,
    trim_trailing: bool,
) -> int:
    if not trim_trailing or length <= 0:
        return length
    entity_end = offset + length
    current_offset = 0
    trimmed_length = 0
    for char in chunk_text:
        char_start = current_offset
        char_end = char_start + _utf16_len(char)
        current_offset = char_end
        if char_start < offset:
            continue
        if char_end > entity_end:
            break
        if not char.isspace():
            trimmed_length = char_end - offset
    return trimmed_length


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2
