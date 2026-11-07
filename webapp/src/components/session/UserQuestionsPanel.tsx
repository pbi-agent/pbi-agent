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
import { Kbd } from "../ui/kbd";
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
    <div className="shrink-0 animate-in px-5 py-3 fade-in" data-user-questions-panel>
      <Card className="mx-auto w-full max-w-6xl">
        <CardHeader>
          <div className="flex min-w-0 items-start gap-3">
            <span aria-hidden="true" className="inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary *:size-4">
              <HelpCircleIcon />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle>
                Assistant needs your input
              </CardTitle>
              <CardDescription>
                {totalQuestions > 1
                  ? `Answer all ${totalQuestions} questions so the assistant can continue this turn.`
                  : "Answer the question so the assistant can continue this turn."}
              </CardDescription>
            </div>
            {totalQuestions > 1 ? (
              <Badge
                variant="outline"
                aria-live="polite"
                className="shrink-0"
              >
                {currentIndex + 1} / {totalQuestions}
              </Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
        <div
          ref={interactiveAreaRef}
          role="group"
          aria-label={`Question ${currentIndex + 1} of ${totalQuestions}`}
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          className="outline-none"
        >
          <fieldset
            key={currentQuestion.question_id}
            className="flex min-w-0 flex-col gap-3 border-0"
          >
            <legend className="mb-3 text-sm font-medium">
              {totalQuestions > 1
                ? `${currentIndex + 1}. ${currentQuestion.question}`
                : currentQuestion.question}
            </legend>
            <div className="flex flex-col gap-2">
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
                    className="h-auto w-full justify-between whitespace-normal"
                    onClick={() => {
                      setSelection(index as SuggestionIndex);
                    }}
                  >
                    <span className="min-w-0 flex-1 text-left">
                      {suggestion}
                    </span>
                    {isRecommended ? (
                      <Badge
                        variant={isSelected ? "secondary" : "outline"}
                        className="shrink-0"
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
                "flex flex-col gap-2 rounded-md border p-3",
                currentDraft.customText.trim() ? "border-primary/40 bg-primary/5" : "border-border",
              )}
              data-state={currentDraft.customText.trim() ? "selected" : "idle"}
            >
              <label
                htmlFor={customId}
                className="flex items-center gap-2 text-sm font-medium"
              >
                <span>Additional note</span>
                {currentDraft.customText.trim() ? (
                  <Badge variant="secondary">
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
                onChange={(event) => {
                  updateDraft(currentQuestion.question_id, {
                    customText: event.target.value,
                  });
                }}
              />
              <p
                id={customDescriptionId}
                className="text-xs text-muted-foreground"
              >
                Optional note sent with your selected suggestion. Press{" "}
                <Kbd>Esc</Kbd>{" "}
                to return to the options.
              </p>
            </div>
          </fieldset>
        </div>
        </CardContent>
        <CardFooter>
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {totalQuestions > 1 ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={currentIndex === 0}
                onClick={() => goToQuestion(currentIndex - 1)}
                aria-label="Previous question"
              >
                <ChevronLeftIcon data-icon="inline-start" />
                Prev
              </Button>
              <div
                className="flex items-center gap-1"
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
                      data-step-state={isActive ? "active" : answered ? "answered" : "empty"}
                      className={cn(
                        "h-1.5 w-4.5 rounded-full transition hover:-translate-y-px",
                        isActive
                          ? "bg-primary"
                          : answered
                            ? "bg-primary/45 hover:bg-primary/65"
                            : "bg-muted-foreground/35 hover:bg-muted-foreground/55",
                      )}
                    />
                  );
                })}
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={currentIndex === totalQuestions - 1}
                onClick={() => goToQuestion(currentIndex + 1)}
                aria-label="Next question"
              >
                Next
                <ChevronRightIcon data-icon="inline-end" />
              </Button>
            </>
          ) : (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd>{" "}
              navigate ·{" "}
              <Kbd>Enter</Kbd>{" "}
              confirm
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {errorMessage ? (
            <p className="text-sm text-destructive" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <Button
            type="button"
            disabled={!canSubmit || isSubmitting}
            onClick={() => {
              void submitAnswers();
            }}
          >
            <SendIcon data-icon="inline-start" />
            {isSubmitting ? "Sending…" : "Send answers"}
          </Button>
        </div>
        </div>
        </CardFooter>
      </Card>
    </div>
  );
}
