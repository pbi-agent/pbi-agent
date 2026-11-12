import userEvent from "@testing-library/user-event";
import { render, screen } from "@testing-library/react";
import { TooltipProvider } from "./ui/tooltip";
import { TruncatedText } from "./TruncatedText";

function clip(element: HTMLElement) {
  Object.defineProperty(element, "scrollWidth", { configurable: true, value: 400 });
  Object.defineProperty(element, "clientWidth", { configurable: true, value: 200 });
}

function treatFocusAsKeyboardFocus(element: HTMLElement) {
  const matches = element.matches.bind(element);
  vi.spyOn(element, "matches").mockImplementation(
    (selector: string) => selector === ":focus-visible" || matches(selector),
  );
}

function tree(text: string, transitionKey?: string) {
  return (
    <TooltipProvider>
      <a href="/target">
        <TruncatedText transitionKey={transitionKey}>{text}</TruncatedText>
      </a>
    </TooltipProvider>
  );
}

describe("TruncatedText", () => {
  it("does not animate when the text changes together with its subject", () => {
    const { rerender } = render(tree("First session", "session-1"));

    rerender(tree("Second session", "session-2"));

    expect(screen.getByText("Second session")).not.toHaveAttribute("data-text-transition");
  });

  it("does not animate the first text given to a subject", () => {
    const { rerender } = render(tree("Untitled session"));

    rerender(tree("first message placeholder", "session-1"));
    expect(screen.getByText("first message placeholder")).not.toHaveAttribute(
      "data-text-transition",
    );

    rerender(tree("Generated title", "session-1"));
    expect(screen.getByText("Generated title")).toHaveAttribute("data-text-transition");
  });

  it("closes an open tooltip when the text changes", async () => {
    const user = userEvent.setup();
    const { rerender } = render(tree("a long placeholder title", "session-1"));
    const placeholder = screen.getByText("a long placeholder title");
    clip(placeholder);
    await user.hover(placeholder);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("a long placeholder title");

    rerender(tree("Short title", "session-1"));

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows the full text when the enclosing link receives keyboard focus", async () => {
    const user = userEvent.setup();
    render(tree("a long clipped title"));
    clip(screen.getByText("a long clipped title"));
    const link = screen.getByRole("link");
    treatFocusAsKeyboardFocus(link);

    await user.tab();
    expect(link).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("a long clipped title");

    await user.tab();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("stays closed on keyboard focus when the text fits", async () => {
    const user = userEvent.setup();
    render(tree("Short"));
    const link = screen.getByRole("link");
    treatFocusAsKeyboardFocus(link);

    await user.tab();

    expect(link).toHaveFocus();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
