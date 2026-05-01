import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("Button", () => {
  it("uses generous horizontal padding for default text actions", () => {
    render(<Button>Save</Button>);

    const button = screen.getByRole("button", { name: "Save" });

    expect(button).toHaveAttribute("data-size", "default");
    expect(button).toHaveClass("px-4");
  });

  it("keeps compact icon buttons square", () => {
    render(
      <Button size="icon-sm" aria-label="Close">
        ×
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Close" });

    expect(button).toHaveAttribute("data-size", "icon-sm");
    expect(button).toHaveClass("size-7");
    expect(button).not.toHaveClass("px-4");
  });
});
