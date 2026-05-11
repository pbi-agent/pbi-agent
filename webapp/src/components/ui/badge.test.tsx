import { render, screen } from "@testing-library/react";
import { Badge } from "./badge";

describe("Badge", () => {
  it.each(["success", "warning", "info", "running", "completed", "failed"] as const)(
    "renders the %s variant data attribute",
    (variant) => {
      render(<Badge variant={variant}>{variant}</Badge>);

      expect(screen.getByText(variant)).toHaveAttribute("data-variant", variant);
    },
  );

  it.each(["running", "completed", "failed"] as const)(
    "renders a semantic dot for %s status badges",
    (variant) => {
      render(<Badge variant={variant}>{variant}</Badge>);

      expect(screen.getByText(variant).querySelector('[data-slot="badge-dot"]')).toBeInTheDocument();
    },
  );

  it("preserves a single slottable child for asChild status badges", () => {
    const { container } = render(
      <Badge asChild variant="running"><a href="/sessions">Running</a></Badge>,
    );

    const link = screen.getByRole("link", { name: "Running" });
    expect(link).toHaveAttribute("data-variant", "running");
    expect(link).toHaveClass("bg-sky-500/10", "text-sky-600");
    expect(container.querySelector('[data-slot="badge-dot"]')).not.toBeInTheDocument();
  });
});
