from pathlib import Path

from pbi_agent.workspace_context import (
    SANDBOX_ENV,
    WORKSPACE_DISPLAY_PATH_ENV,
    WORKSPACE_KEY_ENV,
    resolve_workspace_context,
)


def test_workspace_context_defaults_to_execution_root() -> None:
    context = resolve_workspace_context(
        cwd=Path("/workspace/repo"),
        environ={},
    )

    assert context.execution_root == Path("/workspace/repo")
    assert context.key == "/workspace/repo"
    assert context.directory_key == "/workspace/repo"
    assert context.display_path == "/workspace/repo"
    assert context.is_sandbox is False


def test_workspace_context_uses_host_key_and_display_path_in_sandbox() -> None:
    context = resolve_workspace_context(
        cwd=Path("/workspace/d0918d973e2e241d"),
        environ={
            SANDBOX_ENV: "1",
            WORKSPACE_KEY_ENV: r"C:\Users\Ada\project",
            WORKSPACE_DISPLAY_PATH_ENV: r"C:\Users\Ada\project",
        },
    )

    assert context.execution_root == Path("/workspace/d0918d973e2e241d")
    assert context.key == r"C:\Users\Ada\project"
    assert context.directory_key == r"c:\users\ada\project"
    assert context.display_path == r"C:\Users\Ada\project"
    assert context.is_sandbox is True
