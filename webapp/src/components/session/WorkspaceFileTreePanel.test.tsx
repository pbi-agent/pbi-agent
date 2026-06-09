import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import {
  fetchWorkspaceFileDiff,
  fetchWorkspaceFilePreview,
  fetchWorkspaceFileTree,
} from "../../api";
import {
  getAutoPreviewPanelSize,
  WorkspaceFileTreePanel,
} from "./WorkspaceFileTreePanel";

vi.mock("../../api", () => ({
  fetchWorkspaceFileDiff: vi.fn(),
  fetchWorkspaceFilePreview: vi.fn(),
  fetchWorkspaceFileTree: vi.fn(),
}));

const mockFetchTree = vi.mocked(fetchWorkspaceFileTree);
const mockFetchDiff = vi.mocked(fetchWorkspaceFileDiff);
const mockFetchPreview = vi.mocked(fetchWorkspaceFilePreview);

describe("WorkspaceFileTreePanel", () => {
  let scrollIntoViewMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    scrollIntoViewMock = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoViewMock;
    mockFetchPreview.mockResolvedValue({
      path: "src/app.py",
      content: "print('new')\n",
      size_bytes: 13,
      truncated: false,
      error: null,
    });
    mockFetchDiff.mockResolvedValue({
      path: "src/app.py",
      diff: [
        "diff --git a/src/app.py b/src/app.py",
        "--- a/src/app.py",
        "+++ b/src/app.py",
        "@@ -1 +1 @@",
        "-print('old')",
        "+print('new')",
      ].join("\n"),
      error: null,
    });
  });

  it("renders git modifiers, folder dots, and opens diff first for changed files", async () => {
    const user = userEvent.setup();
    mockFetchTree.mockResolvedValue(treePayload());

    renderWithProviders(
      <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
    );

    expect(screen.queryByRole("button", { name: /Refresh file tree/i })).not.toBeInTheDocument();
    const rootChangedRow = await screen.findByRole("button", { name: /MEMORY\.md/i });
    expect(within(rootChangedRow).getByText("MEMORY.md")).toHaveAttribute(
      "data-git-status",
      "M",
    );

    const srcRow = await screen.findByRole("button", { name: /src/i });
    expect(within(srcRow).getByLabelText("Contains git changes")).toHaveClass(
      "workspace-tree__git-marker",
    );
    await user.click(srcRow);

    const fileRow = await screen.findByRole("button", { name: /app.py/i });
    expect(within(fileRow).getByLabelText("Git status M")).toHaveClass(
      "workspace-tree__git-marker",
    );
    expect(within(fileRow).getByLabelText("Git status M")).toHaveTextContent("M");
    expect(within(fileRow).getByText("app.py")).toHaveAttribute("data-git-status", "M");
    await user.click(fileRow);

    await waitFor(() => {
      expect(mockFetchDiff).toHaveBeenCalledWith("src/app.py");
    });
    await waitFor(() => {
      expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: "start", inline: "nearest" });
    });
    expect(await screen.findByLabelText("Diff summary")).toBeInTheDocument();
    expect(mockFetchPreview).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: "Diff" })).toHaveAttribute("data-state", "on");
    expect(screen.getByRole("radio", { name: "Raw" })).toHaveAttribute("data-state", "off");
    expect(screen.getByRole("radio", { name: "Split" })).toHaveAttribute("data-state", "on");
    expect(screen.getByRole("radio", { name: "Stacked" })).toHaveAttribute("data-state", "off");
    expect(document.querySelector(".git-diff-result")).toHaveAttribute("data-layout", "split");
    const renderedDiffCode = Array.from(
      document.querySelectorAll(".git-diff-result__code code"),
      (node) => node.textContent,
    );
    expect(renderedDiffCode).not.toContain("diff --git a/src/app.py b/src/app.py");
    expect(renderedDiffCode).not.toContain("-1 +1 @@");
    expect(renderedDiffCode).toEqual(
      expect.arrayContaining(["print('old')", "print('new')"]),
    );
    const oldSplitPane = document.querySelector<HTMLDivElement>(
      ".git-diff-result__split-pane--old",
    );
    const newSplitPane = document.querySelector<HTMLDivElement>(
      ".git-diff-result__split-pane--new",
    );
    expect(oldSplitPane).not.toBeNull();
    expect(newSplitPane).not.toBeNull();
    oldSplitPane!.scrollLeft = 48;
    oldSplitPane!.scrollTop = 24;
    fireEvent.scroll(oldSplitPane!);
    expect(newSplitPane!.scrollLeft).toBe(48);
    expect(newSplitPane!.scrollTop).toBe(24);

    await user.click(screen.getByRole("radio", { name: "Stacked" }));
    expect(screen.getByRole("radio", { name: "Split" })).toHaveAttribute("data-state", "off");
    expect(screen.getByRole("radio", { name: "Stacked" })).toHaveAttribute("data-state", "on");
    expect(document.querySelector(".git-diff-result")).toHaveAttribute(
      "data-layout",
      "stacked",
    );

    await user.click(screen.getByRole("radio", { name: "Raw" }));
    await waitFor(() => {
      expect(mockFetchPreview).toHaveBeenCalledWith("src/app.py");
    });
    expect(screen.getByRole("radio", { name: "Diff" })).toHaveAttribute("data-state", "off");
    expect(screen.getByRole("radio", { name: "Raw" })).toHaveAttribute("data-state", "on");
  });

  it("keeps the preview closed until selecting a file and closes it from the preview header", async () => {
    const user = userEvent.setup();
    mockFetchTree.mockResolvedValue(treePayload());

    renderWithProviders(
      <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
    );

    expect(screen.queryByRole("region", { name: "File preview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close file preview" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("separator", { name: "Resize file tree and preview" }),
    ).not.toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: /README\.md/i }));

    expect(await screen.findByRole("region", { name: "File preview" })).toBeInTheDocument();
    await waitFor(() => {
      expect(mockFetchPreview).toHaveBeenCalledWith("README.md");
    });
    expect(
      screen.getByRole("separator", { name: "Resize file tree and preview" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close file preview" }));

    expect(screen.queryByRole("region", { name: "File preview" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("separator", { name: "Resize file tree and preview" }),
    ).not.toBeInTheDocument();
  });

  it("opens the preview when the resizable group already has a measured height", async () => {
    const user = userEvent.setup();
    const getBoundingClientRectSpy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockReturnValue({
        x: 0,
        y: 0,
        width: 320,
        height: 640,
        top: 0,
        right: 320,
        bottom: 640,
        left: 0,
        toJSON: () => ({}),
      } as DOMRect);
    mockFetchTree.mockResolvedValue(treePayload());

    try {
      renderWithProviders(
        <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
      );

      await user.click(await screen.findByRole("button", { name: /README\.md/i }));

      expect(await screen.findByRole("region", { name: "File preview" })).toBeInTheDocument();
      await waitFor(() => {
        expect(mockFetchPreview).toHaveBeenCalledWith("README.md");
      });
    } finally {
      getBoundingClientRectSpy.mockRestore();
    }
  });

  it("filters the tree to changed files only", async () => {
    const user = userEvent.setup();
    mockFetchTree.mockResolvedValue(treePayload());

    renderWithProviders(
      <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
    );

    expect(await screen.findByRole("button", { name: /README\.md/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Show changed files only/i }));

    expect(screen.queryByRole("button", { name: /README\.md/i })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /MEMORY\.md/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /src/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /app\.py/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /src/i }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /app\.py/i })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /MEMORY\.md/i })).toBeInTheDocument();
  });

  it("clears the file search from the styled clear button", async () => {
    const user = userEvent.setup();
    mockFetchTree.mockResolvedValue(treePayload());

    renderWithProviders(
      <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
    );

    const search = screen.getByRole("searchbox", { name: "Search files" });
    await user.type(search, "app");
    expect(search).toHaveValue("app");

    await user.click(screen.getByRole("button", { name: "Clear file search" }));

    expect(search).toHaveValue("");
    expect(search).toHaveFocus();
  });

  it("does not scroll the selected file when toggling folders", async () => {
    const user = userEvent.setup();
    const requestAnimationFrameSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        callback(0);
        return 1;
      });
    mockFetchTree.mockResolvedValue(treePayload());

    try {
      renderWithProviders(
        <WorkspaceFileTreePanel workspaceKey="workspace" onClose={vi.fn()} />,
      );

      const srcRow = await screen.findByRole("button", { name: /src/i });
      await user.click(srcRow);
      await user.click(await screen.findByRole("button", { name: /app\.py/i }));

      expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
      scrollIntoViewMock.mockClear();

      await user.click(srcRow);

      expect(scrollIntoViewMock).not.toHaveBeenCalled();
    } finally {
      requestAnimationFrameSpy.mockRestore();
    }
  });

  it("expands the preview pane to the maximum auto height", () => {
    const tenLines = Array.from({ length: 10 }, (_, index) => `line ${index}`).join("\n");
    const manyLines = Array.from({ length: 80 }, (_, index) => `line ${index}`).join("\n");
    const longWrappedLine = "x".repeat(240);

    expect(getAutoPreviewPanelSize("short", 1000)).toBe("72%");
    expect(getAutoPreviewPanelSize(tenLines, 1000)).toBe("72%");
    expect(getAutoPreviewPanelSize(manyLines, 1000)).toBe("72%");
    expect(getAutoPreviewPanelSize(longWrappedLine, 1000)).toBe("72%");
    expect(getAutoPreviewPanelSize("short", 0)).toBeNull();
  });
});

function treePayload() {
  return {
    items: [
      { path: "MEMORY.md", kind: "file" as const, git_status: "M" as const },
      { path: "README.md", kind: "file" as const, git_status: null },
      { path: "src/app.py", kind: "file" as const, git_status: "M" as const },
    ],
    scan_status: "ready" as const,
    is_stale: false,
    file_count: 2,
    truncated: false,
    error: null,
    git_repository: true,
    git_status_version: "v1",
    git_status_error: null,
  };
}