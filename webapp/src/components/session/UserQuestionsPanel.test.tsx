import { render, screen, within } from "@testing-library/react";
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

describe("UserQuestionsPanel", () => {
  it("preselects the recommended suggestion and submits answers", async () => {
    const onSubmit = vi.fn();
    render(
      <UserQuestionsPanel
        prompt={prompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={onSubmit}
      />,
    );

    const recommended = screen.getByRole("button", { name: /Use RESTRecommended/i });
    expect(recommended).toHaveAttribute("data-variant", "default");

    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_1",
        answer: "Use REST",
        selected_suggestion_index: 0,
        custom: false,
      },
    ]);
  });

  it("submits a custom answer when the text option is used", async () => {
    const onSubmit = vi.fn();
    render(
      <UserQuestionsPanel
        prompt={prompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.type(screen.getByLabelText("Another response"), "Use GraphQL");
    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_1",
        answer: "Use GraphQL",
        selected_suggestion_index: null,
        custom: true,
      },
    ]);
  });

  it("renders exactly three suggestions and a separate custom input", () => {
    render(
      <UserQuestionsPanel
        prompt={prompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={vi.fn()}
      />,
    );

    const panel = screen.getByText(/Which API style should I use\?/).closest("fieldset");
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getAllByRole("button")).toHaveLength(3);
    expect(screen.getByLabelText("Another response")).toBeInTheDocument();
  });

  it("changes the highlighted option with arrow keys", async () => {
    render(
      <UserQuestionsPanel
        prompt={prompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={vi.fn()}
      />,
    );

    const recommended = screen.getByRole("button", {
      name: /Use RESTRecommended/i,
    });
    expect(recommended).toHaveAttribute("data-variant", "default");

    await userEvent.keyboard("{ArrowDown}");
    const second = screen.getByRole("button", { name: "Use WebSocket" });
    expect(second).toHaveAttribute("data-variant", "default");
    expect(recommended).toHaveAttribute("data-variant", "outline");

    await userEvent.keyboard("{ArrowUp}");
    expect(recommended).toHaveAttribute("data-variant", "default");
  });

  it("shows one question at a time with navigation between them", async () => {
    render(
      <UserQuestionsPanel
        prompt={multiPrompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/Which API style should I use\?/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Which database fits best\?/)).toBeNull();

    await userEvent.click(
      screen.getByRole("button", { name: "Next question" }),
    );

    expect(screen.getByText(/Which database fits best\?/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Which API style should I use\?/),
    ).toBeNull();

    await userEvent.keyboard("{ArrowLeft}");
    expect(
      screen.getByText(/Which API style should I use\?/),
    ).toBeInTheDocument();
  });

  it("submits all answers with their per-question selections", async () => {
    const onSubmit = vi.fn();
    render(
      <UserQuestionsPanel
        prompt={multiPrompt}
        isSubmitting={false}
        errorMessage={null}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Use SSE" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Next question" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "SQLite" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Send answers" }),
    );

    expect(onSubmit).toHaveBeenCalledWith([
      {
        question_id: "q_a",
        answer: "Use SSE",
        selected_suggestion_index: 2,
        custom: false,
      },
      {
        question_id: "q_b",
        answer: "SQLite",
        selected_suggestion_index: 1,
        custom: false,
      },
    ]);
  });
});
