from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pbi_agent.tools.types import ToolContext, ToolSpec

if TYPE_CHECKING:
    from pbi_agent.display.protocol import PendingUserQuestion


SPEC = ToolSpec(
    name="ask_user",
    description=(
        "Ask the user one or more clarifying questions and wait for their answers. "
        "Use this only when the user's answer materially changes the next step. "
        "Call ask_user by itself, not in parallel with other tools. Each question "
        "must include exactly three suggestions; suggestion 1 is the recommended default."
    ),
    parameters_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The question to ask the user.",
                        },
                        "suggestions": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 3,
                            "items": {"type": "string"},
                            "description": (
                                "Exactly three suggested answers. The first suggestion "
                                "is treated as the recommended answer."
                            ),
                        },
                    },
                    "required": ["question", "suggestions"],
                },
            }
        },
        "required": ["questions"],
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    display = context.display
    if display is None or not hasattr(display, "ask_user_questions"):
        return {
            "error": {
                "type": "unsupported_display",
                "message": "ask_user is only available in interactive web sessions.",
            }
        }

    questions = _parse_questions(arguments.get("questions"))
    answers = display.ask_user_questions(questions)
    return {
        "responses": [
            {
                "question_id": answer.question_id,
                "question": answer.question,
                "answer": answer.answer,
                "custom": answer.custom,
            }
            for answer in answers
        ]
    }


def _parse_questions(raw_questions: Any) -> list["PendingUserQuestion"]:
    from pbi_agent.display.protocol import PendingUserQuestion

    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("ask_user requires a non-empty questions array.")
    questions: list[PendingUserQuestion] = []
    for index, raw_question in enumerate(raw_questions, start=1):
        if not isinstance(raw_question, dict):
            raise ValueError(f"Question {index} must be an object.")
        question_text = str(raw_question.get("question") or "").strip()
        if not question_text:
            raise ValueError(f"Question {index} must include non-empty question text.")
        raw_suggestions = raw_question.get("suggestions")
        if not isinstance(raw_suggestions, list) or len(raw_suggestions) != 3:
            raise ValueError(
                f"Question {index} must include exactly three suggestions."
            )
        suggestions = [str(value).strip() for value in raw_suggestions]
        if any(not suggestion for suggestion in suggestions):
            raise ValueError(f"Question {index} suggestions must be non-empty strings.")
        questions.append(
            PendingUserQuestion(
                question_id=f"q_{index}",
                question=question_text,
                suggestions=suggestions,
            )
        )
    return questions
