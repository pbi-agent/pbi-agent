import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { renderWithProviders } from "../test/render";
import { useSidebarStore } from "../hooks/useSidebar";
import { AppSidebarLayout } from "./AppSidebar";

function renderSidebar(route: string) {
  return renderWithProviders(
    <AppSidebarLayout contextPanel={<div>Context panel</div>}>
      <div>Main content</div>
    </AppSidebarLayout>,
    { route },
  );
}

describe("AppSidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useSidebarStore.setState({ isOpen: true });
  });

  it("remembers the current session route as the Sessions nav target", async () => {
    renderSidebar("/sessions/session-2");

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Sessions" })).toHaveAttribute(
        "href",
        "/sessions/session-2",
      );
    });
    expect(window.localStorage.getItem("pbi-agent.last-opened-session-id")).toBe("session-2");
  });
});
