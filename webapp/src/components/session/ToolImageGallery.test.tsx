import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolImageGallery } from "./ToolImageGallery";

const images = Array.from({ length: 7 }, (_, i) => ({ key: `k${i}`, path: `img/${i}.png` }));

describe("ToolImageGallery", () => {
  it("renders all thumbnails with workspace image urls", () => {
    render(<ToolImageGallery images={images} />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(7);
    expect(options[0].querySelector("img")?.getAttribute("src")).toBe("/api/files/image?path=img%2F0.png");
  });

  it("moves selection with arrow keys", () => {
    render(<ToolImageGallery images={images} />);
    const list = screen.getByRole("listbox");
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(list, { key: "ArrowLeft" });
    fireEvent.keyDown(list, { key: "ArrowLeft" });
    expect(screen.getAllByRole("option")[6]).toHaveAttribute("aria-selected", "true");
  });

  it("opens fullscreen and navigates with arrows", () => {
    render(<ToolImageGallery images={images} />);
    fireEvent.click(screen.getAllByRole("option")[2]);
    expect(screen.getByRole("dialog")).toHaveTextContent("img/2.png");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByRole("dialog")).toHaveTextContent("img/3.png");
    fireEvent.click(screen.getByLabelText("Previous image"));
    expect(screen.getByRole("dialog")).toHaveTextContent("img/2.png");
  });
});
