import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { fetchWorkspaceFilePreview } from "../../api";
import { TodoPanel, countTodoItems, findTodoFilePaths } from "./TodoPanel";

vi.mock("../../api", () => ({
  fetchWorkspaceFilePreview: vi.fn(),
}));

const mockFetchPreview = vi.mocked(fetchWorkspaceFilePreview);

const ROOT_TODO = [
  "# Tasks",
  "",
  "- [x] Ship the button",
  "- [ ] Write docs",
  "- [>] Review layout",
  "- [!] Waiting on API",
  "- [-] Old idea",
  "- plain bullet",
  "",
].join("\n");

function preview(path: string, content: string) {
  return { path, content, size_bytes: content.length, truncated: false, error: null };
}

describe("findTodoFilePaths", () => {
  it("returns TODO.md files at any depth, root first", () => {
    expect(
      findTodoFilePaths([
        "src/pkg/TODO.md",
        "README.md",
        "docs/todo.md",
        "TODO.md",
        "notes/TODO.md.bak",
        "MYTODO.md",
      ]),
    ).toEqual(["TODO.md", "docs/todo.md", "src/pkg/TODO.md"]);
  });
});

describe("countTodoItems", () => {
  it("counts each marker and skips fenced code", () => {
    const counts = countTodoItems(`${ROOT_TODO}\n\`\`\`md\n- [ ] not a task\n\`\`\`\n`);
    expect(counts).toEqual({
      done: 1,
      pending: 1,
      progress: 1,
      blocked: 1,
      dropped: 1,
      total: 5,
    });
  });
});

describe("TodoPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPreview.mockImplementation((path: string) =>
      Promise.resolve(
        preview(path, path === "TODO.md" ? ROOT_TODO : "- [ ] Nested task\n"),
      ),
    );
  });

  it("renders TODO markdown with status icons and counts", async () => {
    renderWithProviders(
      <TodoPanel paths={["TODO.md"]} workspaceKey="ws" />,
    );

    const panel = await screen.findByRole("complementary", { name: "TODO" });
    expect(await within(panel).findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    expect(mockFetchPreview).toHaveBeenCalledWith("TODO.md");

    const statusOf = (text: string) =>
      within(panel).getByText(text).closest("li")?.getAttribute("data-todo-status");
    expect(statusOf("Ship the button")).toBe("done");
    expect(statusOf("Write docs")).toBe("pending");
    expect(statusOf("Review layout")).toBe("progress");
    expect(statusOf("Waiting on API")).toBe("blocked");
    expect(statusOf("Old idea")).toBe("dropped");
    expect(statusOf("plain bullet")).toBeNull();

    // Markers are replaced by icons, not left as text or disabled checkboxes.
    expect(within(panel).queryByText(/\[>\]/)).not.toBeInTheDocument();
    expect(within(panel).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(panel).getByRole("img", { name: "Blocked" })).toBeInTheDocument();

    expect(within(panel).getByText("1/4 done")).toBeInTheDocument();
    expect(within(panel).getByText("1 blocked")).toBeInTheDocument();
  });

  it("filters items by status when a count badge is clicked", async () => {
    const user = userEvent.setup();
    mockFetchPreview.mockResolvedValue(
      preview(
        "TODO.md",
        [
          "- [x] Ship the button",
          "- [ ] Write docs",
          "- [!] Waiting on API",
          "- [x] Parent epic",
          "  - [!] Nested blocker",
          "  - [x] Nested done",
          "- plain bullet",
          "",
        ].join("\n"),
      ),
    );
    renderWithProviders(<TodoPanel paths={["TODO.md"]} workspaceKey="ws" />);

    const panel = await screen.findByRole("complementary", { name: "TODO" });
    await within(panel).findByText("Write docs");
    const blocked = within(panel).getByRole("button", { name: "2 blocked" });
    expect(blocked).toHaveAttribute("aria-pressed", "false");

    await user.click(blocked);

    expect(blocked).toHaveAttribute("aria-pressed", "true");
    expect(within(panel).getByText("Waiting on API")).toBeInTheDocument();
    expect(within(panel).getByText("Nested blocker")).toBeInTheDocument();
    // The parent stays as context for its matching sub-item.
    expect(within(panel).getByText("Parent epic")).toBeInTheDocument();
    expect(within(panel).queryByText("Ship the button")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Write docs")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Nested done")).not.toBeInTheDocument();
    expect(within(panel).queryByText("plain bullet")).not.toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "1 pending" }));
    expect(within(panel).getByText("Write docs")).toBeInTheDocument();
    expect(within(panel).queryByText("Waiting on API")).not.toBeInTheDocument();
    expect(blocked).toHaveAttribute("aria-pressed", "false");

    // Clicking the active badge clears the filter.
    await user.click(within(panel).getByRole("button", { name: "1 pending" }));
    expect(within(panel).getByText("Ship the button")).toBeInTheDocument();
    expect(within(panel).getByText("plain bullet")).toBeInTheDocument();
  });

  it("switches between several TODO files with tabs", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TodoPanel paths={["TODO.md", "pkg/TODO.md"]} workspaceKey="ws" />,
    );

    const panel = await screen.findByRole("complementary", { name: "TODO" });
    await within(panel).findByText("Ship the button");

    await user.click(within(panel).getByRole("tab", { name: "pkg/TODO.md" }));

    expect(await within(panel).findByText("Nested task")).toBeInTheDocument();
    expect(mockFetchPreview).toHaveBeenCalledWith("pkg/TODO.md");
  });

  it("shows an empty state when the workspace has no TODO.md", async () => {
    renderWithProviders(<TodoPanel paths={[]} workspaceKey="ws" />);

    const panel = await screen.findByRole("complementary", { name: "TODO" });
    expect(within(panel).getByText("No TODO.md")).toBeInTheDocument();
    expect(mockFetchPreview).not.toHaveBeenCalled();
  });

  it("reports preview errors", async () => {
    mockFetchPreview.mockResolvedValue({
      path: "TODO.md",
      content: null,
      size_bytes: 9_000_000,
      truncated: true,
      error: "too_large",
    });
    renderWithProviders(
      <TodoPanel paths={["TODO.md"]} workspaceKey="ws" />,
    );

    await waitFor(() => {
      expect(screen.getByText("This file is too large to preview.")).toBeInTheDocument();
    });
  });
});
