from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DISCOVERY_ROOT = Path(".agents")


@dataclass(slots=True, frozen=True)
class McpServerConfig:
    name: str
    transport: str
    enabled: bool = True
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    location: Path = Path()


def format_project_mcp_servers_markdown(workspace: Path | None = None) -> str:
    servers = discover_mcp_server_configs(workspace)
    if not servers:
        return "### MCP Servers\n\nNo project MCP servers discovered under `.agents/`."

    lines = ["### MCP Servers", ""]
    for server in servers:
        if server.transport == "http":
            lines.append(f"- `{server.name}`: `http {server.url}`")
        else:
            command = " ".join([server.command or "", *server.args]).strip()
            lines.append(f"- `{server.name}`: `{command}`")
            if server.cwd is not None:
                lines.append(f"  `cwd: {server.cwd}`")
        lines.append(f"  `config: {server.location}`")
    return "\n".join(lines)


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def discover_mcp_server_configs(workspace: Path | None = None) -> list[McpServerConfig]:
    root = (workspace or Path.cwd()).resolve()
    config_root = root / _DISCOVERY_ROOT
    if not config_root.is_dir():
        return []

    discovered: list[McpServerConfig] = []
    seen_names: set[str] = set()
    for config_path in sorted(config_root.glob("*.json"), key=lambda item: item.name):
        for config in _load_mcp_server_configs(root, config_path):
            if not config.enabled:
                continue
            if config.name in seen_names:
                _warn(
                    f"Skipping MCP config at {config_path}: duplicate server name {config.name!r}."
                )
                continue
            seen_names.add(config.name)
            discovered.append(config)
    return discovered


def _load_mcp_server_configs(
    workspace_root: Path,
    config_path: Path,
) -> list[McpServerConfig]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError:
        _warn(f"Skipping MCP config at {config_path}: file is unreadable.")
        return []
    except json.JSONDecodeError as exc:
        _warn(f"Skipping MCP config at {config_path}: invalid JSON ({exc.msg}).")
        return []

    if not isinstance(payload, dict):
        _warn(
            f"Skipping MCP config at {config_path}: top-level JSON value must be an object."
        )
        return []

    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, dict):
        _warn(f"Skipping MCP config at {config_path}: missing object 'servers'.")
        return []

    discovered: list[McpServerConfig] = []
    for raw_name, raw_config in sorted(
        raw_servers.items(), key=lambda item: str(item[0])
    ):
        config = _normalize_server_config(
            workspace_root=workspace_root,
            config_path=config_path,
            raw_name=raw_name,
            raw_config=raw_config,
        )
        if config is not None:
            discovered.append(config)
    return discovered


def _normalize_server_config(
    *,
    workspace_root: Path,
    config_path: Path,
    raw_name: Any,
    raw_config: Any,
) -> McpServerConfig | None:
    if not isinstance(raw_name, str) or not raw_name.strip():
        _warn(
            f"Skipping MCP config at {config_path}: server key must be a non-empty string."
        )
        return None
    if not isinstance(raw_config, dict):
        _warn(
            f"Skipping MCP config at {config_path}: server {raw_name!r} must be an object."
        )
        return None

    enabled = raw_config.get("enabled", True)
    if not isinstance(enabled, bool):
        _warn(
            f"Skipping MCP config at {config_path}: server {raw_name!r} has non-boolean 'enabled'."
        )
        return None

    transport = raw_config.get("type", "stdio")
    if not isinstance(transport, str) or transport not in {"stdio", "http"}:
        _warn(
            f"Skipping MCP config at {config_path}: server {raw_name!r} has unsupported type."
        )
        return None

    if transport == "http":
        url = raw_config.get("url")
        if not isinstance(url, str) or not url.strip():
            _warn(
                f"Skipping MCP config at {config_path}: server {raw_name!r} is missing non-empty 'url'."
            )
            return None
        headers = _normalize_headers(raw_config.get("headers"), config_path, raw_name)
        if headers is None:
            return None
        return McpServerConfig(
            name=raw_name.strip(),
            transport="http",
            url=url.strip(),
            headers=headers,
            enabled=enabled,
            location=config_path.resolve(),
        )

    command = raw_config.get("command")
    if not isinstance(command, str) or not command.strip():
        _warn(
            f"Skipping MCP config at {config_path}: server {raw_name!r} is missing non-empty 'command'."
        )
        return None
    args = _normalize_args(raw_config.get("args"), config_path, raw_name)
    if args is None:
        return None
    env = _normalize_env(raw_config.get("env"), config_path, raw_name)
    if env is None:
        return None
    cwd = _normalize_cwd(
        workspace_root,
        raw_config.get("cwd", "."),
        config_path,
        raw_name,
    )
    if cwd is None:
        return None

    return McpServerConfig(
        name=raw_name.strip(),
        transport="stdio",
        command=command.strip(),
        args=tuple(args),
        env=env,
        cwd=cwd,
        enabled=enabled,
        location=config_path.resolve(),
    )


def _normalize_args(raw: Any, config_path: Path, server_name: str) -> list[str] | None:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _warn(
            f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'args'; expected list of strings."
        )
        return None
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            _warn(
                f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'args'; expected list of strings."
            )
            return None
        values.append(item)
    return values


def _normalize_env(
    raw: Any,
    config_path: Path,
    server_name: str,
) -> dict[str, str] | None:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _warn(
            f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'env'; expected object."
        )
        return None
    env: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            _warn(
                f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'env'; keys and values must be strings."
            )
            return None
        env[key] = value
    return env


def _normalize_headers(
    raw: Any,
    config_path: Path,
    server_name: str,
) -> dict[str, str] | None:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _warn(
            f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'headers'; expected object."
        )
        return None
    headers: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            _warn(
                f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'headers'; keys and values must be strings."
            )
            return None
        headers[key] = value
    return headers


def _normalize_cwd(
    workspace_root: Path,
    raw: Any,
    config_path: Path,
    server_name: str,
) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        _warn(
            f"Skipping MCP config at {config_path}: server {server_name!r} has invalid 'cwd'; expected non-empty string."
        )
        return None

    candidate = Path(raw)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (workspace_root / candidate).resolve()
    )
    try:
        resolved.relative_to(workspace_root)
    except ValueError:
        _warn(
            f"Skipping MCP config at {config_path}: server {server_name!r} has 'cwd' outside the workspace."
        )
        return None
    return resolved
