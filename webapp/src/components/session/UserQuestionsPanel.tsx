import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  HelpCircleIcon,
  SendIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

import type { PendingUserQuestions, UserQuestionAnswer } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { Textarea } from "../ui/textarea";

type SuggestionIndex = 0 | 1 | 2;
type SelectedIndex = SuggestionIndex | null;

type QuestionDraft = {
  selectedIndex: SelectedIndex;
  customText: string;
};

const NAV_ORDER: readonly SuggestionIndex[] = [0, 1, 2] as const;
const navPositionOf = (idx: SelectedIndex) =>
  idx === null ? -1 : NAV_ORDER.indexOf(idx);

function buildInitialDrafts(
  questions: PendingUserQuestions["questions"],
): Record<string, QuestionDraft> {
  return Object.fromEntries(
    questions.map((question) => [
      question.question_id,
      {
        selectedIndex: null,
        customText: "",
      },
    ]),
  );
}

export function UserQuestionsPanel({
  prompt,
  isSubmitting,
  errorMessage,
  onSubmit,
}: {
  prompt: PendingUserQuestions;
  isSubmitting: boolean;
  errorMessage: string | null;
  onSubmit: (answers: UserQuestionAnswer[]) => Promise<void> | void;
}) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, QuestionDraft>>(() =>
    buildInitialDrafts(prompt.questions),
  );

  // Reset state when a new prompt arrives.
  useEffect(() => {
    setCurrentIndex(0);
    setDrafts(buildInitialDrafts(prompt.questions));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt.prompt_id]);

  const interactiveAreaRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const totalQuestions = prompt.questions.length;
  const currentQuestion = prompt.questions[currentIndex];
  const currentDraft: QuestionDraft = drafts[currentQuestion.question_id] ?? {
    selectedIndex: null,
    customText: "",
  };

  const isQuestionAnswered = (
    question: PendingUserQuestions["questions"][number],
  ): boolean => {
    const draft = drafts[question.question_id];
    if (!draft) return false;
    return draft.selectedIndex !== null;
  };

  const canSubmit = useMemo(
    () => prompt.questions.every(isQuestionAnswered),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [drafts, prompt.questions],
  );

  const updateDraft = (questionId: string, next: Partial<QuestionDraft>) => {
    setDrafts((current) => ({
      ...current,
      [questionId]: {
        ...(current[questionId] ?? { selectedIndex: null, customText: "" }),
        ...next,
      },
    }));
  };

  const focusOption = (idx: SelectedIndex) => {
    queueMicrotask(() => {
      optionRefs.current[idx ?? 0]?.focus();
    });
  };

  const setSelection = (idx: SuggestionIndex) => {
    updateDraft(currentQuestion.question_id, { selectedIndex: idx });
    focusOption(idx);
  };

  const goToQuestion = (targetIndex: number) => {
    if (targetIndex < 0 || targetIndex >= totalQuestions) return;
    setCurrentIndex(targetIndex);
    const draft = drafts[prompt.questions[targetIndex].question_id];
    focusOption(draft?.selectedIndex ?? null);
  };

  const submitAnswers = async () => {
    if (!canSubmit || isSubmitting) return;
    const answers = prompt.questions.map((question) => {
      const draft = drafts[question.question_id] ?? {
        selectedIndex: null,
        customText: "",
      };
      if (draft.selectedIndex === null) {
        throw new Error("Cannot submit unanswered user question.");
      }
      return {
        question_id: question.question_id,
        answer: question.suggestions[draft.selectedIndex],
        selected_suggestion_index: draft.selectedIndex,
        custom: draft.customText.trim().length > 0,
        custom_note: draft.customText.trim() || null,
      } satisfies UserQuestionAnswer;
    });
    await onSubmit(answers);
  };

  // Auto-focus the active option whenever the visible question changes.
  useEffect(() => {
    focusOption(currentDraft.selectedIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt.prompt_id, currentIndex]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const inTextarea = target.tagName === "TEXTAREA";

    if (inTextarea) {
      const textarea = target as HTMLTextAreaElement;
      if (event.key === "Escape") {
        event.preventDefault();
        if (currentDraft.selectedIndex !== null) {
          focusOption(currentDraft.selectedIndex);
        }
        return;
      }
      // Allow leaving the textarea via ArrowUp when caret is at the very start.
      if (
        event.key === "ArrowUp" &&
        textarea.selectionStart === 0 &&
        textarea.selectionEnd === 0
      ) {
        event.preventDefault();
        if (currentDraft.selectedIndex !== null) {
          focusOption(currentDraft.selectedIndex);
        }
        return;
      }
      // Native arrow / character handling otherwise (text editing).
      return;
    }

    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        const pos = navPositionOf(currentDraft.selectedIndex);
        const nextPos = Math.min(NAV_ORDER.length - 1, Math.max(-1, pos) + 1);
        setSelection(NAV_ORDER[nextPos]);
        break;
      }
      case "ArrowUp": {
        event.preventDefault();
        const pos = navPositionOf(currentDraft.selectedIndex);
        const nextPos = Math.max(0, (pos < 0 ? 0 : pos) - 1);
        setSelection(NAV_ORDER[nextPos]);
        break;
      }
      case "ArrowRight": {
        if (totalQuestions > 1 && currentIndex < totalQuestions - 1) {
          event.preventDefault();
          interactiveAreaRef.current?.focus();
          goToQuestion(currentIndex + 1);
        }
        break;
      }
      case "ArrowLeft": {
        if (totalQuestions > 1 && currentIndex > 0) {
          event.preventDefault();
          interactiveAreaRef.current?.focus();
          goToQuestion(currentIndex - 1);
        }
        break;
      }
      case "Enter": {
        event.preventDefault();
        if (currentIndex < totalQuestions - 1) {
          interactiveAreaRef.current?.focus();
          goToQuestion(currentIndex + 1);
        } else if (canSubmit) {
          void submitAnswers();
        }
        break;
      }
      default:
        break;
    }
  };

  const customId = `${prompt.prompt_id}-${currentQuestion.question_id}-custom`;
  const customDescriptionId = `${customId}-description`;
  return (
    <div className="user-questions-panel">
      <Card className="user-questions-panel__card">
        <CardHeader className="user-questions-panel__header">
          <div className="user-questions-panel__heading">
            <span aria-hidden="true" className="user-questions-panel__icon">
              <HelpCircleIcon />
            </span>
            <div className="user-questions-panel__heading-copy">
              <CardTitle className="user-questions-panel__title">
                Assistant needs your input
              </CardTitle>
              <CardDescription className="user-questions-panel__description">
                {totalQuestions > 1
                  ? `Answer all ${totalQuestions} questions so the assistant can continue this turn.`
                  : "Answer the question so the assistant can continue this turn."}
              </CardDescription>
            </div>
            {totalQuestions > 1 ? (
              <Badge
                variant="outline"
                aria-live="polite"
                className="user-questions-panel__badge"
              >
                {currentIndex + 1} / {totalQuestions}
              </Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="user-questions-panel__content">
        <div
          ref={interactiveAreaRef}
          role="group"
          aria-label={`Question ${currentIndex + 1} of ${totalQuestions}`}
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          className="user-questions-panel__interactive-area"
        >
          <fieldset
            key={currentQuestion.question_id}
            className="user-question-card"
          >
            <legend className="user-question-card__legend">
              {totalQuestions > 1
                ? `${currentIndex + 1}. ${currentQuestion.question}`
                : currentQuestion.question}
            </legend>
            <div className="user-question-card__options">
              {currentQuestion.suggestions.map((suggestion, index) => {
                const isSelected = currentDraft.selectedIndex === index;
                const isRecommended =
                  index === currentQuestion.recommended_suggestion_index;
                return (
                  <Button
                    key={suggestion}
                    ref={(element) => {
                      optionRefs.current[index] = element;
                    }}
                    type="button"
                    variant={isSelected ? "default" : "outline"}
                    aria-pressed={isSelected}
                    data-question-option=""
                    data-selected={isSelected ? "true" : "false"}
                    className={cn(
                      "user-question-option",
                      isSelected && "user-question-option--selected",
                    )}
                    onClick={() => {
                      setSelection(index as SuggestionIndex);
                    }}
                  >
                    <span className="user-question-option__label">
                      {suggestion}
                    </span>
                    {isRecommended ? (
                      <Badge
                        variant={isSelected ? "secondary" : "outline"}
                        className="user-question-option__badge"
                      >
                        Recommended
                      </Badge>
                    ) : null}
                  </Button>
                );
              })}
            </div>
            <div
              className={cn(
                "user-question-custom",
                currentDraft.customText.trim()
                  ? "user-question-custom--selected"
                  : "user-question-custom--idle",
              )}
              data-state={currentDraft.customText.trim() ? "selected" : "idle"}
            >
              <label
                htmlFor={customId}
                className="user-question-custom__label"
              >
                <span>Additional note</span>
                {currentDraft.customText.trim() ? (
                  <Badge variant="secondary" className="user-question-custom__badge">
                    Included
                  </Badge>
                ) : null}
              </label>
              <Textarea
                id={customId}
                ref={textareaRef}
                value={currentDraft.customText}
                placeholder="Add optional context for your selected suggestion…"
                aria-describedby={customDescriptionId}
                rows={2}
                className="user-question-custom__textarea"
                onChange={(event) => {
                  updateDraft(currentQuestion.question_id, {
                    customText: event.target.value,
                  });
                }}
              />
              <p
                id={customDescriptionId}
                className="user-question-custom__description"
              >
                Optional note sent with your selected suggestion. Press{" "}
                <kbd className="user-questions-panel__kbd">
                  Esc
                </kbd>{" "}
                to return to the options.
              </p>
            </div>
          </fieldset>
        </div>
        </CardContent>
        <CardFooter className="user-questions-panel__footer">
        <div className="user-questions-panel__navigation">
          {totalQuestions > 1 ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="user-questions-panel__nav-button"
                disabled={currentIndex === 0}
                onClick={() => goToQuestion(currentIndex - 1)}
                aria-label="Previous question"
              >
                <ChevronLeftIcon data-icon="inline-start" />
                Prev
              </Button>
              <div
                className="user-questions-panel__steps"
                role="presentation"
                aria-hidden="true"
              >
                {prompt.questions.map((question, i) => {
                  const answered = isQuestionAnswered(question);
                  const isActive = i === currentIndex;
                  return (
                    <button
                      key={question.question_id}
                      type="button"
                      tabIndex={-1}
                      aria-label={`Go to question ${i + 1}`}
                      onClick={() => goToQuestion(i)}
                      className={cn(
                        "user-questions-panel__step",
                        isActive
                          ? "user-questions-panel__step--active"
                          : answered
                            ? "user-questions-panel__step--answered"
                            : "user-questions-panel__step--empty",
                      )}
                    />
                  );
                })}
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="user-questions-panel__nav-button"
                disabled={currentIndex === totalQuestions - 1}
                onClick={() => goToQuestion(currentIndex + 1)}
                aria-label="Next question"
              >
                Next
                <ChevronRightIcon data-icon="inline-end" />
              </Button>
            </>
          ) : (
            <span className="user-questions-panel__hint">
              <kbd className="user-questions-panel__kbd">
                ↑
              </kbd>
              <kbd className="user-questions-panel__kbd">
                ↓
              </kbd>{" "}
              navigate ·{" "}
              <kbd className="user-questions-panel__kbd">
                Enter
              </kbd>{" "}
              confirm
            </span>
          )}
        </div>
        <div className="user-questions-panel__actions">
          {errorMessage ? (
            <p className="user-questions-panel__error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <Button
            type="button"
            disabled={!canSubmit || isSubmitting}
            className="user-questions-panel__submit"
            onClick={() => {
              void submitAnswers();
            }}
          >
            <SendIcon data-icon="inline-start" />
            {isSubmitting ? "Sending…" : "Send answers"}
          </Button>
        </div>
        </CardFooter>
      </Card>
    </div>
  );
}
