import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const { highlightCodeMock } = vi.hoisted(() => ({
  highlightCodeMock:
    vi.fn<(code: string, language: string) => Promise<string | null>>(),
}));
highlightCodeMock.mockResolvedValue(null);

vi.mock("@/lib/shiki-highlighter", () => ({
  highlightCode: highlightCodeMock,
}));

import { ToolResult } from "./ToolResult";

describe("ToolResult", () => {
  describe("ShellToolResult", () => {
    it("renders the command in the header while the tool is running", () => {
      render(
        <ToolResult
          running
          text="$ bun run web:build"
          metadata={{
            tool_name: "shell",
            call_id: "call_1",
            status: "running",
            arguments: {
              command: "bun run web:build",
              working_directory: ".",
              timeout_ms: 180000,
            },
          }}
        />,
      );

      expect(screen.getByText("bun run web:build")).toBeInTheDocument();
      expect(screen.queryByText("Summary")).not.toBeInTheDocument();
      expect(screen.queryByText("$ bun run web:build")).not.toBeInTheDocument();
      expect(screen.queryByText("<missing command>")).not.toBeInTheDocument();
    });

    it("shows a Running status label while the tool is running", () => {
      render(
        <ToolResult
          running
          text="$ ls"
          metadata={{
            tool_name: "shell",
            call_id: "call_1",
            status: "running",
            arguments: { command: "ls", working_directory: ".", timeout_ms: 180000 },
          }}
        />,
      );

      expect(screen.getByText("Running")).toBeInTheDocument();
      expect(screen.queryByText(/Exit undefined/)).not.toBeInTheDocument();
    });

    it("renders the exit code once the shell tool completes", () => {
      render(
        <ToolResult
          text="$ ls"
          metadata={{
            tool_name: "shell",
            call_id: "call_1",
            status: "completed",
            success: true,
            arguments: { command: "ls", working_directory: ".", timeout_ms: 180000 },
            command: "ls",
            working_directory: ".",
            timeout_ms: 180000,
            exit_code: 0,
            timed_out: false,
            result: { stdout: "README.md\n", stderr: "", exit_code: 0 },
          }}
        />,
      );

      expect(screen.getByText("Done")).toBeInTheDocument();
    });

    it("falls back to the missing command placeholder when no command is provided", () => {
      render(
        <ToolResult
          running
          text=""
          metadata={{
            tool_name: "shell",
            call_id: "call_1",
            status: "running",
          }}
        />,
      );

      expect(screen.getByText("<missing command>")).toBeInTheDocument();
    });

    describe("stdout highlighting", () => {
      beforeEach(() => {
        highlightCodeMock.mockReset();
        highlightCodeMock.mockResolvedValue(null);
      });

      it("highlights stdout as the language inferred from a `cat <file>` command", async () => {
        const { container } = render(
          <ToolResult
            text=""
            metadata={{
              tool_name: "shell",
              call_id: "call_cat_py",
              status: "completed",
              success: true,
              command: "cat src/main.py",
              working_directory: ".",
              exit_code: 0,
              arguments: { command: "cat src/main.py" },
              result: { stdout: "print('hi')\n", stderr: "", exit_code: 0 },
            }}
          />,
        );

        await waitFor(() => {
          expect(highlightCodeMock).toHaveBeenCalledWith(
            "print('hi')\n",
            "python",
          );
        });

        expect(
          container.querySelector('[data-language="python"]'),
        ).not.toBeNull();
      });

      it("highlights `git diff` stdout as a unified diff", async () => {
        render(
          <ToolResult
            text=""
            metadata={{
              tool_name: "shell",
              call_id: "call_git_diff",
              status: "completed",
              success: true,
              command: "git diff",
              working_directory: ".",
              exit_code: 0,
              arguments: { command: "git diff" },
              result: {
                stdout: "diff --git a/x b/x\n--- a/x\n+++ b/x\n",
                stderr: "",
                exit_code: 0,
              },
            }}
          />,
        );

        await waitFor(() => {
          expect(highlightCodeMock).toHaveBeenCalledWith(
            "diff --git a/x b/x\n--- a/x\n+++ b/x\n",
            "diff",
          );
        });
      });

      it("leaves stdout plain when the command is unrecognized", () => {
        const { container } = render(
          <ToolResult
            text=""
            metadata={{
              tool_name: "shell",
              call_id: "call_ls",
              status: "completed",
              success: true,
              command: "ls -la",
              working_directory: ".",
              exit_code: 0,
              arguments: { command: "ls -la" },
              result: { stdout: "README.md\nsrc\n", stderr: "", exit_code: 0 },
            }}
          />,
        );

        expect(highlightCodeMock).not.toHaveBeenCalled();
        const stdoutPre = container.querySelector(
          ".tool-result__section pre.tool-result__pre",
        );
        expect(stdoutPre?.textContent).toBe("README.md\nsrc\n");
        expect(stdoutPre?.getAttribute("data-highlighted")).toBe("false");
      });

      it("does not request highlighting for the (empty) placeholder", () => {
        render(
          <ToolResult
            text=""
            metadata={{
              tool_name: "shell",
              call_id: "call_cat_empty",
              status: "completed",
              success: true,
              command: "cat src/main.py",
              working_directory: ".",
              exit_code: 0,
              arguments: { command: "cat src/main.py" },
              result: { stdout: "", stderr: "", exit_code: 0 },
            }}
          />,
        );

        expect(highlightCodeMock).not.toHaveBeenCalled();
        expect(screen.getAllByText("(empty)").length).toBeGreaterThan(0);
      });
    });
  });

  describe("File-edit tools", () => {
    const editDiff = "@@ TODO.md\n-[ ] Old\n+[X] New\n";

    it.each(["apply_patch", "replace_in_file", "write_file"])(
      "renders %s completion with the git-diff layout",
      (toolName) => {
        const { container } = render(
          <ToolResult
            text=""
            metadata={{
              tool_name: toolName,
              call_id: `call_${toolName}`,
              status: "completed",
              success: true,
              path: "TODO.md",
              operation: "update_file",
              diff: editDiff,
              arguments: { path: "TODO.md", old_string: "Old", new_string: "New" },
              result: { status: "completed", message: "ok", replacements: 1 },
            }}
          />,
        );

        expect(container.querySelector(".git-diff-result")).not.toBeNull();
        expect(container.querySelector(".tool-result-card")).toBeNull();
        expect(
          container.querySelector(".git-diff-result__title")?.textContent,
        ).toBe("TODO.md");
      },
    );

    it("renders a compact file-edit card while a tool is still running", () => {
      const { container } = render(
        <ToolResult
          running
          text=""
          metadata={{
            tool_name: "apply_patch",
            call_id: "call_running",
            status: "running",
            path: "TODO.md",
            operation: "update_file",
            operation_count: 1,
            arguments: "*** Begin Patch\n*** Update File: TODO.md\n@@\n-Old\n+New\n*** End Patch\n",
          }}
        />,
      );

      expect(container.querySelector(".git-diff-result")).toBeNull();
      expect(container.querySelector(".tool-result-card")).not.toBeNull();
      expect(screen.getByText("TODO.md")).toBeInTheDocument();
      expect(screen.getByText("Updating")).toBeInTheDocument();
      expect(screen.getByText("Running")).toBeInTheDocument();
      expect(screen.queryByText("Arguments")).not.toBeInTheDocument();
    });
  });

  describe("ReadFileToolResult", () => {
    beforeEach(() => {
      highlightCodeMock.mockReset();
      highlightCodeMock.mockResolvedValue(null);
    });

    it("derives the language from the file extension for the Content section", async () => {
      const { container } = render(
        <ToolResult
          text=""
          metadata={{
            tool_name: "read_file",
            call_id: "call_read_py",
            status: "completed",
            success: true,
            arguments: { path: "src/main.py" },
            result: { path: "src/main.py", content: "print('hi')\n" },
          }}
        />,
      );

      await waitFor(() => {
        expect(highlightCodeMock).toHaveBeenCalledWith(
          "print('hi')\n",
          "python",
        );
      });

      const codeWrapper = container.querySelector(
        '.tool-result__section [data-language="python"]',
      );
      expect(codeWrapper).not.toBeNull();
      expect(screen.getByText("src/main.py")).toBeInTheDocument();
    });

    it("renders plain text without highlighting for unknown extensions", () => {
      const { container } = render(
        <ToolResult
          text=""
          metadata={{
            tool_name: "read_file",
            call_id: "call_read_txt",
            status: "completed",
            success: true,
            arguments: { path: "notes.unknownext" },
            result: { path: "notes.unknownext", content: "hello" },
          }}
        />,
      );

      expect(highlightCodeMock).not.toHaveBeenCalled();
      const pre = container.querySelector(
        ".tool-result__section pre.tool-result__pre",
      );
      expect(pre?.textContent).toBe("hello");
      expect(pre?.getAttribute("data-highlighted")).toBe("false");
    });

    it("highlights tabular schema as markdown", async () => {
      render(
        <ToolResult
          text=""
          metadata={{
            tool_name: "read_file",
            call_id: "call_read_csv",
            status: "completed",
            success: true,
            arguments: { path: "data.csv" },
            result: {
              path: "data.csv",
              schema: "- column_a: int64\n- column_b: object",
              preview: "| column_a | column_b |\n| --- | --- |\n| 1 | x |",
              rows: 100,
              columns: 2,
            },
          }}
        />,
      );

      await waitFor(() => {
        expect(highlightCodeMock).toHaveBeenCalledWith(
          "- column_a: int64\n- column_b: object",
          "markdown",
        );
        expect(highlightCodeMock).toHaveBeenCalledWith(
          "| column_a | column_b |\n| --- | --- |\n| 1 | x |",
          "markdown",
        );
      });
    });
  });
});
