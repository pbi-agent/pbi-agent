import { useEffect, useMemo, useRef, type FormEvent } from "react";
import { HelpCircleIcon, SendIcon } from "lucide-react";

import type { PendingUserQuestions, UserQuestionAnswer } from "../../types";
import { Badge } from "../ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { Kbd } from "../ui/kbd";
import {
  Questionnaire,
  QuestionnaireActions,
  QuestionnaireChoice,
  QuestionnaireChoices,
  QuestionnaireError,
  QuestionnaireInput,
  QuestionnaireItem,
  QuestionnaireNext,
  QuestionnairePrevious,
  QuestionnaireProgress,
  QuestionnaireSubmit,
  QuestionnaireTitle,
} from "../ui/questionnaire";

type PendingQuestion = PendingUserQuestions["questions"][number];

const SUGGESTION_INDEXES = [0, 1, 2] as const;

function choiceValue(index: number): string {
  return String(index);
}

function readAnswer(
  form: HTMLFormElement,
  question: PendingQuestion,
): UserQuestionAnswer | null {
  const name = CSS.escape(question.question_id);
  const checked = form.querySelector<HTMLInputElement>(
    `input[type="radio"][name="${name}"]:checked`,
  );
  if (checked) {
    const index = Number(checked.value);
    const suggestion = question.suggestions[index];
    if (suggestion === undefined || (index !== 0 && index !== 1 && index !== 2)) {
      return null;
    }
    return {
      question_id: question.question_id,
      answer: suggestion,
      selected_suggestion_index: index,
      custom: false,
      custom_note: null,
    };
  }
  // The freeform input only carries the item name while it is the active answer.
  const freeform = form.querySelector<HTMLInputElement>(
    `input[data-slot="questionnaire-input"][name="${name}"]`,
  );
  const text = freeform?.value.trim() ?? "";
  if (!text) return null;
  return {
    question_id: question.question_id,
    answer: text,
    selected_suggestion_index: null,
    custom: true,
    custom_note: null,
  };
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
  const formRef = useRef<HTMLFormElement>(null);
  const totalQuestions = prompt.questions.length;

  const items = useMemo(
    () =>
      prompt.questions.map((question) => ({
        name: question.question_id,
        required: true,
        choices: SUGGESTION_INDEXES.map((index) => ({ value: choiceValue(index) })),
      })),
    [prompt.questions],
  );

  // Focus the first answer of a newly arrived prompt so shortcuts and arrows work immediately.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      formRef.current
        ?.querySelector<HTMLInputElement>("fieldset:not([hidden]) input[type=\"radio\"]")
        ?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [prompt.prompt_id]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    const form = event.currentTarget;
    const answers: UserQuestionAnswer[] = [];
    for (const question of prompt.questions) {
      const answer = readAnswer(form, question);
      if (!answer) return;
      answers.push(answer);
    }
    void onSubmit(answers);
  };

  return (
    <div className="shrink-0 animate-in px-5 py-3 fade-in" data-user-questions-panel>
      <Questionnaire
        key={prompt.prompt_id}
        ref={formRef}
        items={items}
        shortcuts="numbers"
        onSubmit={handleSubmit}
        aria-label="Assistant questions"
        className="mx-auto max-w-6xl"
      >
        <Card className="w-full">
          <CardHeader>
            <div className="flex min-w-0 items-start gap-3">
              <span
                aria-hidden="true"
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary *:size-4"
              >
                <HelpCircleIcon />
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
                <QuestionnaireProgress
                  className="w-auto min-w-0 shrink-0"
                  render={(props, state) => (
                    <div {...props}>
                      <Badge variant="outline">
                        {state.current} / {state.total}
                      </Badge>
                    </div>
                  )}
                />
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {prompt.questions.map((question, questionIndex) => (
              <QuestionnaireItem
                key={question.question_id}
                name={question.question_id}
                required
              >
                <QuestionnaireTitle>
                  {totalQuestions > 1
                    ? `${questionIndex + 1}. ${question.question}`
                    : question.question}
                </QuestionnaireTitle>
                <QuestionnaireChoices>
                  {SUGGESTION_INDEXES.map((index) => (
                    <QuestionnaireChoice
                      key={index}
                      value={choiceValue(index)}
                      data-question-option=""
                    >
                      <span className="flex min-w-0 items-center justify-between gap-2">
                        <span className="min-w-0">{question.suggestions[index]}</span>
                        {index === question.recommended_suggestion_index ? (
                          <Badge variant="secondary" className="shrink-0">
                            Recommended
                          </Badge>
                        ) : null}
                      </span>
                    </QuestionnaireChoice>
                  ))}
                  <QuestionnaireInput
                    aria-label="Another answer"
                    placeholder="Or type your own answer…"
                    autoComplete="off"
                  />
                </QuestionnaireChoices>
                <QuestionnaireError>
                  Choose a suggestion or type your own answer to continue.
                </QuestionnaireError>
              </QuestionnaireItem>
            ))}
          </CardContent>
          <CardFooter className="flex-col items-stretch">
            {errorMessage ? (
              <p className="text-sm text-destructive" role="alert">
                {errorMessage}
              </p>
            ) : null}
            <QuestionnaireActions>
              <QuestionnairePrevious size="sm">Previous</QuestionnairePrevious>
              <QuestionnaireNext size="sm">Next</QuestionnaireNext>
              <QuestionnaireSubmit size="sm" disabled={isSubmitting}>
                <SendIcon data-icon="inline-start" />
                {isSubmitting ? "Sending…" : "Send answers"}
              </QuestionnaireSubmit>
            </QuestionnaireActions>
            <p className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground max-sm:hidden">
              <Kbd>1</Kbd>
              <Kbd>2</Kbd>
              <Kbd>3</Kbd> choose · <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> move · <Kbd>Enter</Kbd> continue
            </p>
          </CardFooter>
        </Card>
      </Questionnaire>
    </div>
  );
}
