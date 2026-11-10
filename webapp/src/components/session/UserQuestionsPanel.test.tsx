import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { PendingUserQuestions } from "../../types";
import { UserQuestionsPanel } from "./UserQuestionsPanel";

const prompt: PendingUserQuestions = {
  prompt_id: "ask-1",
  questions: [
    {
      question_id: "q_1",
      question: "Which API style should I use?",
      suggestions: ["Use REST", "Use WebSocket", "Use SSE"],
      recommended_suggestion_index: 0,
    },
  ],
};

const multiPrompt: PendingUserQuestions = {
  prompt_id: "ask-multi",
  questions: [
    {
      question_id: "q_a",
      question: "Which API style should I use?",
      suggestions: ["Use REST", "Use WebSocket", "Use SSE"],
      recommended_suggestion_index: 0,
    },
    {
      question_id: "q_b",
      question: "Which database fits best?",
      suggestions: ["Postgres", "SQLite", "MongoDB"],
      recommended_suggestion_index: 0,
    },
  ],
};

function renderPanel(
  value: PendingUserQuestions,
  onSubmit = vi.fn(),
  props: { isSubmitting?: boolean; errorMessage?: string | null } = {},
) {
  render(
    <UserQuestionsPanel
      prompt={value}
      isSubmitting={props.isSubmitting ?? false}
      errorMessage={props.errorMessage ?? null}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

describe("UserQuestionsPanel", () => {
  it("renders the three suggestions as radios plus a freeform answer", () => {
    renderPanel(prompt);

    const group = screen.getByRole("group", { name: "Which API style should I use?" });
    expect(group.tagName).toBe("FIELDSET");
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("radio", { name: /Use REST/ })).not.toBeChecked();
    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Another answer" })).toBeInTheDocument();
  });

  it("requires an explicit answer before submitting", async () => {
    const onSubmit = renderPanel(prompt);

    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText("Choose a suggestion or type your own answer to continue."),
    ).toBeVisible();

    await userEvent.click(screen.getByRole("radio", { name: /Use REST/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_1",
        answer: "Use REST",
        selected_suggestion_index: 0,
        custom: false,
        custom_note: null,
      },
    ]);
  });

  it("submits a freeform answer instead of a suggestion", async () => {
    const onSubmit = renderPanel(prompt);

    await userEvent.click(screen.getByRole("radio", { name: /Use SSE/ }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Another answer" }),
      "Use GraphQL subscriptions",
    );
    expect(screen.getByRole("radio", { name: /Use SSE/ })).not.toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_1",
        answer: "Use GraphQL subscriptions",
        selected_suggestion_index: null,
        custom: true,
        custom_note: null,
      },
    ]);
  });

  it("selects suggestions with number shortcuts", async () => {
    const onSubmit = renderPanel(prompt);

    await waitFor(() => expect(screen.getByRole("radio", { name: /Use REST/ })).toHaveFocus());
    await userEvent.keyboard("2");
    expect(screen.getByRole("radio", { name: /Use WebSocket/ })).toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));
    expect(onSubmit).toHaveBeenCalledWith([
      expect.objectContaining({ answer: "Use WebSocket", selected_suggestion_index: 1 }),
    ]);
  });

  it("shows one question at a time and submits every answer", async () => {
    const onSubmit = renderPanel(multiPrompt);

    expect(screen.getByRole("progressbar")).toHaveTextContent("1 / 2");
    expect(screen.getByRole("group", { name: /Which API style/ })).toBeVisible();
    expect(screen.queryByRole("group", { name: /Which database/ })).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: /Use SSE/ }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByRole("progressbar")).toHaveTextContent("2 / 2");
    expect(screen.getByRole("group", { name: /Which database/ })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("radio", { name: /Use SSE/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    await userEvent.click(screen.getByRole("radio", { name: /SQLite/ }));
    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_a",
        answer: "Use SSE",
        selected_suggestion_index: 2,
        custom: false,
        custom_note: null,
      },
      {
        question_id: "q_b",
        answer: "SQLite",
        selected_suggestion_index: 1,
        custom: false,
        custom_note: null,
      },
    ]);
  });

  it("does not advance past an unanswered question", async () => {
    renderPanel(multiPrompt);

    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByRole("group", { name: /Which API style/ })).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveTextContent("1 / 2");
  });

  it("disables sending while a submission is in flight and shows errors", () => {
    renderPanel(prompt, vi.fn(), { isSubmitting: true, errorMessage: "Request failed" });

    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Request failed");
  });
});
