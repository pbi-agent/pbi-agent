import { render, screen } from "@testing-library/react";
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
  });
});
