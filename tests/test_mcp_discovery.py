from __future__ import annotations

from pathlib import Path

from pbi_agent.mcp.discovery import (
    McpServerConfig,
    discover_mcp_server_configs,
    format_project_mcp_servers_markdown,
)


def _write_config(root: Path, name: str, payload: str) -> Path:
    config_dir = root / ".agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / name
    path.write_text(payload, encoding="utf-8")
    return path


def test_discover_mcp_server_configs_loads_valid_servers_from_map(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        "mcp.json",
        (
            "{"
            '"servers":{'
            '"echo":{"command":"uv","args":["run","server.py"],"env":{"TOKEN":"abc"},"cwd":"."},'
            '"github":{"type":"http","url":"https://example.test/mcp"}'
            "}"
            "}"
        ),
    )

    configs = discover_mcp_server_configs(tmp_path)

    assert configs == [
        McpServerConfig(
            name="echo",
            transport="stdio",
            command="uv",
            args=("run", "server.py"),
            env={"TOKEN": "abc"},
            cwd=tmp_path.resolve(),
            enabled=True,
            location=config_path.resolve(),
        ),
        McpServerConfig(
            name="github",
            transport="http",
            url="https://example.test/mcp",
            headers={},
            enabled=True,
            location=config_path.resolve(),
        ),
    ]


def test_discover_mcp_server_configs_ignores_non_mcp_json_files(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        "other.json",
        '{"servers":{"echo":{"command":"uv","cwd":"."}}}',
    )

    configs = discover_mcp_server_configs(tmp_path)

    assert configs == []


def test_discover_mcp_server_configs_skips_invalid_cwd(tmp_path: Path, capsys) -> None:
    _write_config(
        tmp_path,
        "mcp.json",
        '{"servers":{"echo":{"command":"uv","cwd":"../outside"}}}',
    )

    configs = discover_mcp_server_configs(tmp_path)

    assert configs == []
    assert "outside the workspace" in capsys.readouterr().err


def test_format_project_mcp_servers_markdown_lists_servers(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        "mcp.json",
        (
            "{"
            '"servers":{'
            '"echo":{"command":"uv","args":["run","server.py"],"cwd":"."},'
            '"github":{"type":"http","url":"https://example.test/mcp"}'
            "}"
            "}"
        ),
    )

    result = format_project_mcp_servers_markdown(tmp_path)

    assert "### MCP Servers" in result
    assert "- `echo`: `uv run server.py`" in result
    assert f"`cwd: {tmp_path.resolve()}`" in result
    assert "- `github`: `http https://example.test/mcp`" in result
    assert f"`config: {config_path.resolve()}`" in result


def test_format_project_mcp_servers_markdown_handles_empty_workspace(
    tmp_path: Path,
) -> None:
    result = format_project_mcp_servers_markdown(tmp_path)

    assert result == (
        "### MCP Servers\n\nNo project MCP servers discovered under `.agents/`."
    )
