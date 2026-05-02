from __future__ import annotations

import threading

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
