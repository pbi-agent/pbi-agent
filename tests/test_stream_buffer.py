from __future__ import annotations

from pbi_agent.tools.stream_buffer import StreamBuffer


def test_stream_buffer_keeps_everything_under_limits() -> None:
    buffer = StreamBuffer(head_max=10, tail_max=10)
    buffer.append("hello ")
    buffer.append("world")

    assert buffer.text() == "hello world"
    assert buffer.dropped is False
    assert buffer.total == 11


def test_stream_buffer_keeps_head_and_tail_and_marks_dropped_middle() -> None:
    buffer = StreamBuffer(head_max=4, tail_max=4)
    buffer.append("HEAD")
    buffer.append("middle-part")
    buffer.append("TAIL")

    assert buffer.dropped is True
    assert buffer.text() == "HEAD\n... 11 chars dropped ...\nTAIL"


def test_stream_buffer_keeps_tail_of_oversized_chunk() -> None:
    buffer = StreamBuffer(head_max=2, tail_max=3)
    buffer.append("ab" + "x" * 20 + "xyz")

    assert buffer.text() == "ab\n... 20 chars dropped ...\nxyz"


def test_stream_buffer_read_since_returns_only_new_output() -> None:
    buffer = StreamBuffer(head_max=100, tail_max=100)
    buffer.append("first\n")
    first = buffer.read_since(0)
    buffer.append("second\n")
    second = buffer.read_since(first.cursor)

    assert first.text == "first\n"
    assert second.text == "second\n"
    assert second.skipped == 0
    assert buffer.read_since(second.cursor).text == ""


def test_stream_buffer_read_since_reports_skipped_middle() -> None:
    buffer = StreamBuffer(head_max=4, tail_max=4)
    buffer.append("HEAD")
    seen = buffer.read_since(0)
    buffer.append("0123456789TAIL")

    unseen = buffer.read_since(seen.cursor)

    assert unseen.text == "TAIL"
    assert unseen.skipped == 10
    assert unseen.cursor == 18
