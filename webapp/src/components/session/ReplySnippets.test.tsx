import userEvent from "@testing-library/user-event";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { Composer, type ComposerHandle } from "./Composer";
import { ReplySelectionPopover } from "./ReplySelectionPopover";
import { renderWithProviders } from "../../test/render";

function selectText(node: Node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  range.getBoundingClientRect = () => new DOMRect(100, 200, 80, 16);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
}

describe("reply to selection", () => {
  it("shows Reply for assistant selections and submits the comment", async () => {
    const user = userEvent.setup();
    const onAddReply = vi.fn();
    renderWithProviders(
      <>
        <div data-timeline-entry="assistant">
          <div data-timeline-content><p>Assistant answer</p></div>
        </div>
        <div data-timeline-entry="user">
          <div data-timeline-content><p>User text</p></div>
        </div>
        <ReplySelectionPopover onAddReply={onAddReply} />
      </>,
    );

    selectText(screen.getByText("User text"));
    fireEvent.mouseUp(document);
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(screen.queryByRole("button", { name: "Reply" })).not.toBeInTheDocument();

    selectText(screen.getByText("Assistant answer"));
    fireEvent.mouseUp(document);
    await user.click(await screen.findByRole("button", { name: "Reply" }));
    const input = screen.getByRole("textbox", { name: "Reply comment" });
    await user.type(input, "Please explain{Enter}");
    expect(onAddReply).toHaveBeenCalledWith("Assistant answer", "Please explain");
    expect(screen.queryByRole("dialog", { name: "Reply to selection" })).not.toBeInTheDocument();
  });

  it("sends reply snippets with xml tags alongside composer text", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn<(payload: { text: string; images: File[] }) => Promise<void>>()
      .mockResolvedValue(undefined);
    const ref = createRef<ComposerHandle>();
    renderWithProviders(
      <Composer
        ref={ref}
        inputEnabled
        sessionEnded={false}
        liveSessionId="live-1"
        supportsImageInputs
        interactiveMode={false}
        isSubmitting={false}
        onSubmit={onSubmit}
      />,
    );
    act(() => {
      ref.current!.addReplySnippet("first quote", "first comment");
      ref.current!.addReplySnippet("second quote", "second comment");
    });
    expect(screen.getAllByTestId("reply-snippet-card")).toHaveLength(2);
    await user.click(screen.getAllByRole("button", { name: "Remove reply snippet" })[1]);
    expect(screen.getAllByTestId("reply-snippet-card")).toHaveLength(1);

    await user.type(screen.getByRole("textbox"), "Overall note{Enter}");
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const text = onSubmit.mock.calls[0][0].text;
    expect(text).toContain("<quoted_text>\nfirst quote\n</quoted_text>");
    expect(text).toContain("<user_comment>\nfirst comment\n</user_comment>");
    expect(text).not.toContain("second quote");
    expect(text.endsWith("Overall note")).toBe(true);
    expect(screen.queryByTestId("reply-snippet-card")).not.toBeInTheDocument();
  });
});
