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

const CUSTOM_OPTION = -1;

type SelectedIndex = 0 | 1 | 2 | typeof CUSTOM_OPTION;

type QuestionDraft = {
  selectedIndex: SelectedIndex;
  customText: string;
};

const NAV_ORDER: readonly SelectedIndex[] = [0, 1, 2, CUSTOM_OPTION] as const;
const navPositionOf = (idx: SelectedIndex) => NAV_ORDER.indexOf(idx);

function buildInitialDrafts(
  questions: PendingUserQuestions["questions"],
): Record<string, QuestionDraft> {
  return Object.fromEntries(
    questions.map((question) => [
      question.question_id,
      {
        selectedIndex: (question.recommended_suggestion_index ?? 0) as SelectedIndex,
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
    selectedIndex: 0,
    customText: "",
  };

  const isQuestionAnswered = (
    question: PendingUserQuestions["questions"][number],
  ): boolean => {
    const draft = drafts[question.question_id];
    if (!draft) return false;
    if (draft.selectedIndex === CUSTOM_OPTION) {
      return draft.customText.trim().length > 0;
    }
    return draft.selectedIndex >= 0 && draft.selectedIndex <= 2;
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
        ...(current[questionId] ?? { selectedIndex: 0 as const, customText: "" }),
        ...next,
      },
    }));
  };

  const focusOption = (idx: SelectedIndex) => {
    queueMicrotask(() => {
      if (idx === CUSTOM_OPTION) {
        textareaRef.current?.focus();
      } else {
        optionRefs.current[idx]?.focus();
      }
    });
  };

  const setSelection = (idx: SelectedIndex) => {
    updateDraft(currentQuestion.question_id, { selectedIndex: idx });
    focusOption(idx);
  };

  const goToQuestion = (targetIndex: number) => {
    if (targetIndex < 0 || targetIndex >= totalQuestions) return;
    setCurrentIndex(targetIndex);
    const draft = drafts[prompt.questions[targetIndex].question_id];
    focusOption(draft?.selectedIndex ?? 0);
  };

  const submitAnswers = async () => {
    if (!canSubmit || isSubmitting) return;
    const answers = prompt.questions.map((question) => {
      const draft = drafts[question.question_id] ?? {
        selectedIndex: 0 as const,
        customText: "",
      };
      if (draft.selectedIndex === CUSTOM_OPTION) {
        return {
          question_id: question.question_id,
          answer: draft.customText.trim(),
          selected_suggestion_index: null,
          custom: true,
        } satisfies UserQuestionAnswer;
      }
      return {
        question_id: question.question_id,
        answer: question.suggestions[draft.selectedIndex],
        selected_suggestion_index: draft.selectedIndex,
        custom: false,
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
        setSelection(2);
        return;
      }
      // Allow leaving the textarea via ArrowUp when caret is at the very start.
      if (
        event.key === "ArrowUp" &&
        textarea.selectionStart === 0 &&
        textarea.selectionEnd === 0
      ) {
        event.preventDefault();
        setSelection(2);
        return;
      }
      // Native arrow / character handling otherwise (text editing).
      return;
    }

    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        const pos = navPositionOf(currentDraft.selectedIndex);
        const nextPos = Math.min(NAV_ORDER.length - 1, Math.max(0, pos) + 1);
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
          goToQuestion(currentIndex + 1);
        }
        break;
      }
      case "ArrowLeft": {
        if (totalQuestions > 1 && currentIndex > 0) {
          event.preventDefault();
          goToQuestion(currentIndex - 1);
        }
        break;
      }
      case "Enter": {
        event.preventDefault();
        if (currentIndex < totalQuestions - 1) {
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
  const customInvalid =
    currentDraft.selectedIndex === CUSTOM_OPTION &&
    !currentDraft.customText.trim();

  return (
    <Card className="user-questions-panel border border-primary/20 ring-0">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"
          >
            <HelpCircleIcon className="size-4" />
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <CardTitle>Assistant needs your input</CardTitle>
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
              className="shrink-0 self-start"
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
            className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0"
          >
            <legend className="mb-1 text-sm font-semibold leading-snug text-foreground">
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
                    className={cn(
                      "h-auto min-h-10 justify-between gap-3 whitespace-normal px-3 py-2 text-left",
                      isSelected
                        ? "shadow-sm"
                        : "hover:border-primary/40 hover:bg-primary/5",
                    )}
                    onClick={() => {
                      setSelection(index as SelectedIndex);
                    }}
                  >
                    <span className="flex-1 text-left">{suggestion}</span>
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
                "rounded-lg border bg-background p-3 transition-colors",
                currentDraft.selectedIndex === CUSTOM_OPTION
                  ? "border-primary/60 bg-primary/5"
                  : "border-border hover:border-primary/40",
              )}
              data-state={
                currentDraft.selectedIndex === CUSTOM_OPTION ? "selected" : "idle"
              }
            >
              <label
                htmlFor={customId}
                className="flex items-center justify-between gap-2 text-sm font-medium"
              >
                <span>Another response</span>
                {currentDraft.selectedIndex === CUSTOM_OPTION ? (
                  <Badge variant="secondary" className="shrink-0">
                    Selected
                  </Badge>
                ) : null}
              </label>
              <Textarea
                id={customId}
                ref={textareaRef}
                value={currentDraft.customText}
                placeholder="Write a custom answer…"
                aria-invalid={customInvalid}
                aria-describedby={customDescriptionId}
                rows={2}
                className="mt-2 min-h-[3.25rem]"
                onFocus={() => {
                  updateDraft(currentQuestion.question_id, {
                    selectedIndex: CUSTOM_OPTION,
                  });
                }}
                onChange={(event) => {
                  updateDraft(currentQuestion.question_id, {
                    selectedIndex: CUSTOM_OPTION,
                    customText: event.target.value,
                  });
                }}
              />
              <p
                id={customDescriptionId}
                className="mt-1.5 text-xs text-muted-foreground"
              >
                Use this if none of the suggestions fit. Press{" "}
                <kbd className="rounded border border-border bg-muted px-1 text-[10px] font-medium">
                  Esc
                </kbd>{" "}
                to return to the options.
              </p>
            </div>
          </fieldset>
        </div>
      </CardContent>
      <CardFooter className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
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
                className="flex items-center gap-1.5"
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
                        "h-1.5 w-4 rounded-full transition-colors",
                        isActive
                          ? "bg-primary"
                          : answered
                            ? "bg-primary/40 hover:bg-primary/60"
                            : "bg-muted-foreground/30 hover:bg-muted-foreground/50",
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
            <span className="text-xs text-muted-foreground">
              <kbd className="rounded border border-border bg-muted px-1 text-[10px] font-medium">
                ↑
              </kbd>
              <kbd className="ml-1 rounded border border-border bg-muted px-1 text-[10px] font-medium">
                ↓
              </kbd>{" "}
              navigate ·{" "}
              <kbd className="rounded border border-border bg-muted px-1 text-[10px] font-medium">
                Enter
              </kbd>{" "}
              confirm
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {errorMessage ? (
            <p className="m-0 text-sm text-destructive" role="alert">
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
      </CardFooter>
    </Card>
  );
}
