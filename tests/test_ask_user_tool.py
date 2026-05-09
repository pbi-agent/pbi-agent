from __future__ import annotations

import threading
import time

import pytest

from pbi_agent.display.protocol import PendingUserQuestion, UserQuestionAnswer
from pbi_agent.tools.ask_user import handle
from pbi_agent.tools.registry import get_tool_specs
from pbi_agent.tools.types import ToolContext
from pbi_agent.web.display import WebDisplay


def test_ask_user_tool_is_registered_but_excludable() -> None:
    assert any(spec.name == "ask_user" for spec in get_tool_specs())
    assert all(
        spec.name != "ask_user" for spec in get_tool_specs(excluded_names={"ask_user"})
    )


def test_ask_user_tool_returns_answers_without_selected_suggestion_index() -> None:
    class AskingDisplay:
        def ask_user_questions(
            self, questions: list[PendingUserQuestion]
        ) -> list[UserQuestionAnswer]:
            return [
                UserQuestionAnswer(
                    question_id=questions[0].question_id,
                    question=questions[0].question,
                    answer="Use REST",
                    custom=False,
                )
            ]

    result = handle(
        {
            "questions": [
                {
                    "question": "Which API style?",
                    "suggestions": ["Use REST", "Use WS", "Use SSE"],
                }
            ]
        },
        ToolContext(display=AskingDisplay()),  # type: ignore[arg-type]
    )

    assert result == {
        "responses": [
            {
                "question_id": "q_1",
                "question": "Which API style?",
                "answer": "Use REST",
                "custom": False,
            }
        ]
    }
    assert "selected_suggestion_index" not in result["responses"][0]


def test_web_display_asks_and_waits_for_question_response() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    display = WebDisplay(
        publish_event=lambda event, payload: events.append((event, payload))
    )
    result: list[UserQuestionAnswer] = []

    def ask() -> None:
        result.extend(
            display.ask_user_questions(
                [
                    PendingUserQuestion(
                        question_id="q_1",
                        question="Proceed?",
                        suggestions=["Yes", "No", "Later"],
                    )
                ]
            )
        )

    worker = threading.Thread(target=ask)
    worker.start()
    while not events:
        worker.join(timeout=0.01)
    requested = events[0][1]
    display.submit_question_response(
        prompt_id=str(requested["prompt_id"]),
        answers=[
            UserQuestionAnswer(
                question_id="q_1",
                question="Proceed?",
                answer="Yes",
                custom=False,
            )
        ],
    )
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert result == [
        UserQuestionAnswer(
            question_id="q_1",
            question="Proceed?",
            answer="Yes",
            custom=False,
        )
    ]
    assert [event for event, _payload in events] == [
        "user_questions_requested",
        "user_questions_resolved",
    ]
    assert requested["questions"] == [
        {
            "question_id": "q_1",
            "question": "Proceed?",
            "suggestions": ["Yes", "No", "Later"],
            "recommended_suggestion_index": 0,
        }
    ]


def test_web_display_deduplicates_waiting_input_state_events() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    display = WebDisplay(
        publish_event=lambda event, payload: events.append((event, payload))
    )
    result: list[object] = []

    worker = threading.Thread(target=lambda: result.append(display.user_prompt()))
    worker.start()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if events:
            break
        time.sleep(0.01)

    time.sleep(0.65)
    display.submit_input("hello")
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert result
    assert [event for event, _payload in events] == ["input_state", "input_state"]
    assert [payload for _event, payload in events] == [
        {"enabled": True},
        {"enabled": False},
    ]


def test_web_display_direct_command_holds_input_disabled_until_finished() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    display = WebDisplay(
        publish_event=lambda event, payload: events.append((event, payload))
    )
    result: list[object] = []

    worker = threading.Thread(target=lambda: result.append(display.user_prompt()))
    worker.start()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if events:
            break
        time.sleep(0.01)
    assert events == [("input_state", {"enabled": True})]

    display.begin_direct_command()
    assert events[-1] == ("input_state", {"enabled": False})
    event_count_while_blocked = len(events)
    time.sleep(0.65)
    assert len(events) == event_count_while_blocked

    display.finish_direct_command()
    assert events[-1] == ("input_state", {"enabled": True})
    display.submit_input("hello")
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert result
    assert [event for event, _payload in events] == [
        "input_state",
        "input_state",
        "input_state",
        "input_state",
    ]
    assert [payload for _event, payload in events] == [
        {"enabled": True},
        {"enabled": False},
        {"enabled": True},
        {"enabled": False},
    ]


def test_web_display_direct_command_releases_hold_when_disable_publish_fails() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    fail_next_disable = True

    def publish(event: str, payload: dict[str, object]) -> None:
        nonlocal fail_next_disable
        if event == "input_state" and payload.get("enabled") is False:
            if fail_next_disable:
                fail_next_disable = False
                raise RuntimeError("persist failed")
        events.append((event, payload))

    display = WebDisplay(publish_event=publish)

    with pytest.raises(RuntimeError, match="persist failed"):
        display.begin_direct_command()

    result: list[object] = []
    worker = threading.Thread(target=lambda: result.append(display.user_prompt()))
    worker.start()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if events:
            break
        time.sleep(0.01)

    display.submit_input("hello")
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert result
    assert [event for event, _payload in events] == ["input_state", "input_state"]
    assert [payload for _event, payload in events] == [
        {"enabled": True},
        {"enabled": False},
    ]


def test_web_display_direct_command_does_not_enable_active_turn_input() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    display = WebDisplay(
        publish_event=lambda event, payload: events.append((event, payload))
    )

    display.submit_input("turn in progress")
    display.begin_direct_command()
    display.finish_direct_command()

    assert events == [("input_state", {"enabled": False})]


def test_web_display_direct_command_does_not_restore_stale_input_state() -> None:
    events: list[tuple[str, dict[str, object]]] = []
    display = WebDisplay(
        publish_event=lambda event, payload: events.append((event, payload))
    )
    result: list[object] = []

    worker = threading.Thread(target=lambda: result.append(display.user_prompt()))
    worker.start()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if events:
            break
        time.sleep(0.01)
    assert events == [("input_state", {"enabled": True})]

    display.begin_direct_command()
    display.submit_input("queued while command is running")
    worker.join(timeout=1)
    display.finish_direct_command()
    time.sleep(0.05)

    assert not worker.is_alive()
    assert result
    assert [event for event, _payload in events] == ["input_state", "input_state"]
    assert [payload for _event, payload in events] == [
        {"enabled": True},
        {"enabled": False},
    ]
