"""Tests for Display tool-call formatting methods."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from pbi_agent.agent.session import NEW_CHAT_SENTINEL
from pbi_agent.ui.display import Display


def _make_display(*, verbose: bool = False) -> Display:
    """Create a Display with a stub app for unit-testing format helpers."""
    app = MagicMock()
    return Display(app, verbose=verbose)


# -- _format_skill_knowledge_item -------------------------------------------


class TestFormatSkillKnowledgeItem:
    def test_single_skill(self) -> None:
        d = _make_display()
        result = d._format_skill_knowledge_item(
            ["card_visual"], status="[green]done[/green]"
        )
        assert "card_visual" in result
        assert "[green]done[/green]" in result

    def test_multiple_skills(self) -> None:
        d = _make_display()
        result = d._format_skill_knowledge_item(
            ["card_visual", "table_visual"], status="[green]done[/green]"
        )
        assert "card_visual, table_visual" in result

    def test_empty_skills_shows_none(self) -> None:
        d = _make_display()
        result = d._format_skill_knowledge_item([], status="[green]done[/green]")
        assert "<none>" in result

    def test_verbose_includes_call_id(self) -> None:
        d = _make_display(verbose=True)
        result = d._format_skill_knowledge_item(
            ["card_visual"], status="[green]done[/green]", call_id="call_42"
        )
        assert "call_42" in result

    def test_non_verbose_omits_call_id(self) -> None:
        d = _make_display(verbose=False)
        result = d._format_skill_knowledge_item(
            ["card_visual"], status="[green]done[/green]", call_id="call_42"
        )
        assert "call_42" not in result


# -- _format_init_report_item -----------------------------------------------


class TestFormatInitReportItem:
    def test_shows_destination(self) -> None:
        d = _make_display()
        result = d._format_init_report_item(".", status="[green]done[/green]")
        assert "." in result
        assert "[green]done[/green]" in result

    def test_force_true_shown(self) -> None:
        d = _make_display()
        result = d._format_init_report_item(
            "/tmp/report", status="[green]done[/green]", force=True
        )
        assert "force" in result
        assert "true" in result

    def test_force_false_omitted(self) -> None:
        d = _make_display()
        result = d._format_init_report_item(
            "/tmp/report", status="[green]done[/green]", force=False
        )
        assert "force" not in result

    def test_verbose_includes_call_id(self) -> None:
        d = _make_display(verbose=True)
        result = d._format_init_report_item(
            ".", status="[green]done[/green]", call_id="call_7"
        )
        assert "call_7" in result


# -- _format_generic_function_item (enhanced) --------------------------------


class TestFormatGenericFunctionItem:
    def test_non_verbose_with_args_shows_summary(self) -> None:
        d = _make_display(verbose=False)
        result = d._format_generic_function_item(
            "my_tool",
            status="[green]done[/green]",
            arguments={"key": "value"},
        )
        assert "my_tool()" in result
        assert "key" in result
        assert "value" in result

    def test_non_verbose_no_args_shows_name_only(self) -> None:
        d = _make_display(verbose=False)
        result = d._format_generic_function_item(
            "my_tool",
            status="[green]done[/green]",
            arguments=None,
        )
        assert "my_tool()" in result
        assert "[green]done[/green]" in result
        assert "\n" not in result

    def test_non_verbose_empty_dict_args_shows_name_only(self) -> None:
        d = _make_display(verbose=False)
        result = d._format_generic_function_item(
            "my_tool",
            status="[green]done[/green]",
            arguments={},
        )
        assert "my_tool()" in result
        assert "[green]done[/green]" in result
        assert "\n" not in result

    def test_verbose_includes_call_id_and_args(self) -> None:
        d = _make_display(verbose=True)
        result = d._format_generic_function_item(
            "my_tool",
            status="[green]done[/green]",
            call_id="call_99",
            arguments={"key": "value"},
        )
        assert "call_id=call_99" in result
        assert "args=" in result


class TestRenderThinking:
    def test_missing_body_uses_summary_text(self) -> None:
        app = MagicMock()
        display = Display(app)
        summary = (
            "I need to summarize the content, possibly mentioning if there are any "
            "continuities present. This full text should reach the widget body."
        )

        display.render_thinking(title=summary)

        assert app.call_from_thread.call_count == 1
        _, widget_id, widget_title, widget_body = app.call_from_thread.call_args.args
        assert widget_id == "thinking-1"
        assert widget_title == "Thinking..."
        assert widget_body == summary

    def test_ellipsis_body_uses_summary_text(self) -> None:
        app = MagicMock()
        display = Display(app)
        summary = (
            "I need to summarize the content, possibly mentioning if there are any "
            "continuities present. This should replace ellipsis-only content."
        )

        display.render_thinking("...", title=summary)

        assert app.call_from_thread.call_count == 1
        _, _, widget_title, widget_body = app.call_from_thread.call_args.args
        assert widget_title == "Thinking..."
        assert widget_body == summary


class TestInteractiveInputQueue:
    def test_new_chat_request_queued_before_prompt_is_preserved(self) -> None:
        display = _make_display()
        result: list[str] = []

        display.request_new_chat()

        worker = threading.Thread(target=lambda: result.append(display.user_prompt()))
        worker.start()
        worker.join(timeout=1)

        assert not worker.is_alive()
        assert result == [NEW_CHAT_SENTINEL]


# -- function_result routing -------------------------------------------------


class TestFunctionResultRouting:
    """Verify function_result routes skill_knowledge and init_report properly."""

    def test_skill_knowledge_routed(self) -> None:
        d = _make_display()
        d.function_result(
            "skill_knowledge",
            True,
            call_id="call_sk",
            arguments={"skills": ["card_visual", "table_visual"]},
        )
        assert len(d._tool_group.items) == 1
        text = d._tool_group.items[0].text
        assert "card_visual" in text
        assert "table_visual" in text

    def test_init_report_routed(self) -> None:
        d = _make_display()
        d.function_result(
            "init_report",
            True,
            call_id="call_ir",
            arguments={"dest": "/my/report", "force": True},
        )
        assert len(d._tool_group.items) == 1
        text = d._tool_group.items[0].text
        assert "/my/report" in text
        assert "force" in text

    def test_generic_function_routed(self) -> None:
        d = _make_display()
        d.function_result(
            "some_unknown_tool",
            False,
            call_id="call_u",
            arguments={"x": 1},
        )
        assert len(d._tool_group.items) == 1
        text = d._tool_group.items[0].text
        assert "some_unknown_tool()" in text

    def test_shell_still_routed(self) -> None:
        d = _make_display()
        d.function_result(
            "shell",
            True,
            call_id="call_sh",
            arguments={"command": "ls -la"},
        )
        assert len(d._tool_group.items) == 1
        text = d._tool_group.items[0].text
        assert "ls -la" in text

    def test_apply_patch_still_routed(self) -> None:
        d = _make_display()
        d.function_result(
            "apply_patch",
            True,
            call_id="call_ap",
            arguments={
                "path": "/tmp/file.txt",
                "operation_type": "create",
                "diff": "--- a\n+++ b",
            },
        )
        assert len(d._tool_group.items) == 1
        text = d._tool_group.items[0].text
        assert "/tmp/file.txt" in text
        assert "create" in text
