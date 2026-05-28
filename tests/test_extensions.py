from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, cast

from pbi_agent import extensions
from pbi_agent.agent import session as session_module
from pbi_agent.agent.session.commands import reserved_slash_extension_names
from pbi_agent.config import Settings
from pbi_agent.extensions import (
    discover_extensions,
    find_extension_for_slash,
    format_extensions_markdown,
    run_extension,
    tool_catalog_with_extensions,
)
from pbi_agent.tools.catalog import ToolCatalog, ToolCatalogEntry
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec
from pbi_agent.web.session.catalogs import CatalogsMixin


def _write_command(root: Path, name: str) -> None:
    path = root / ".agents" / "commands" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {name} command.\n---\n\nDo it.",
        encoding="utf-8",
    )


def _write_extension(
    root: Path,
    name: str,
    body: str = "def run(input: dict) -> dict:\n    return {'echo': input}\n",
    *,
    description: str = "Does a thing",
    schema: str = '{ type = "object", properties = { text = { type = "string" } }, additionalProperties = true }',
) -> Path:
    path = root / ".agents" / "extensions" / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# /// script
# dependencies = []
#
# [tool.pbi-agent.extension]
# name = "{name}"
# description = "{description}"
# input_schema = {schema}
# ///

{body}
""",
        encoding="utf-8",
    )
    return path


def _patch_runner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        extensions,
        "_ensure_extension_env",
        lambda definition, env_dir, *, timeout=120.0: None,
    )
    monkeypatch.setattr(
        extensions, "_python_executable", lambda env_dir: Path(sys.executable)
    )

    def write_runner(env_dir: Path) -> Path:
        env_dir.mkdir(parents=True, exist_ok=True)
        runner = env_dir / "runner.py"
        runner.write_text(extensions._RUNNER_SOURCE, encoding="utf-8")
        return runner

    monkeypatch.setattr(extensions, "_write_runner_shim", write_runner)


def _empty_tool_handler(arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
    del arguments, context
    return ToolOutput(result={})


def test_discover_extensions_parses_pep723_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "My Extension")

    discovery = discover_extensions(tmp_path)

    assert [item.name for item in discovery.extensions] == ["my-extension"]
    assert discovery.extensions[0].description == "Does a thing"
    assert discovery.extensions[0].input_schema["type"] == "object"
    assert discovery.diagnostics == []


def test_discover_extensions_reports_invalid_duplicates_and_collisions(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "alpha")
    duplicate = _write_extension(tmp_path, "alpha-two", description="Duplicate")
    duplicate.write_text(
        duplicate.read_text(encoding="utf-8").replace(
            'name = "alpha-two"', 'name = "alpha"'
        ),
        encoding="utf-8",
    )
    bad = tmp_path / ".agents" / "extensions" / "bad.py"
    bad.write_text("print('missing metadata')\n", encoding="utf-8")
    _write_extension(tmp_path, "shell")

    discovery = discover_extensions(tmp_path, reserved_names={"shell"})

    assert [item.name for item in discovery.extensions] == ["alpha"]
    messages = [item.message for item in discovery.diagnostics]
    assert any("missing PEP 723" in message for message in messages)
    assert any("duplicate name" in message for message in messages)
    assert any("collides" in message for message in messages)


def test_run_extension_success_captures_logs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_runner(monkeypatch, tmp_path)
    _write_extension(
        tmp_path,
        "hello",
        "def run(input: dict) -> dict:\n    print('hello log')\n    return {'text': input['text'].upper()}\n",
    )
    definition = discover_extensions(tmp_path).extensions[0]

    result = run_extension(definition, {"text": "hi"}, workspace=tmp_path)

    assert result.ok is True
    assert result.result == {"text": "HI"}
    assert "hello log" in result.stdout


def test_run_extension_captures_child_process_output(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_runner(monkeypatch, tmp_path)
    _write_extension(
        tmp_path,
        "child-output",
        "def run(input: dict) -> dict:\n"
        "    import subprocess\n"
        "    subprocess.run(['printf', 'child out'], check=True)\n"
        "    return {'ok': True}\n",
    )
    definition = discover_extensions(tmp_path).extensions[0]

    result = run_extension(definition, {}, workspace=tmp_path)

    assert result.ok is True
    assert result.result == {"ok": True}
    assert "child out" in result.stdout


def test_run_extension_bounds_large_child_process_output(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_runner(monkeypatch, tmp_path)
    _write_extension(
        tmp_path,
        "large-output",
        "def run(input: dict) -> dict:\n"
        "    import subprocess\n"
        "    subprocess.run(['printf', 'x' * 20000], check=True)\n"
        "    return {'ok': True}\n",
    )
    definition = discover_extensions(tmp_path).extensions[0]

    result = run_extension(definition, {}, workspace=tmp_path)

    assert result.ok is True
    assert result.result == {"ok": True}
    assert result.stdout_truncated is True
    assert "bytes omitted" in result.stdout
    assert len(result.stdout) < 5000


def test_ensure_extension_env_serializes_first_use_setup(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "serial-setup")
    definition = discover_extensions(tmp_path).extensions[0]
    env_dir = tmp_path / "extension-env"
    calls: list[list[str]] = []
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_run(cmd, **kwargs):
        del kwargs
        nonlocal active, max_active
        assert not (env_dir / ".setup.lock").exists()
        if cmd[:2] == ["uv", "venv"]:
            assert not env_dir.exists()
        with lock:
            calls.append(list(cmd))
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.1)
        if cmd[:2] == ["uv", "venv"]:
            env_dir.mkdir(parents=True)
        with lock:
            active -= 1
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(extensions.subprocess, "run", fake_run)
    errors: list[BaseException] = []

    def ensure() -> None:
        try:
            extensions._ensure_extension_env(definition, env_dir, timeout=2)
        except BaseException as exc:  # pragma: no cover - assertion reports below
            errors.append(exc)

    threads = [threading.Thread(target=ensure) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(calls) == 1
    assert max_active == 1
    assert (env_dir / "metadata.sha256").read_text(encoding="utf-8") == (
        definition.metadata_fingerprint
    )


def test_ensure_extension_env_clears_existing_env_on_metadata_change(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "stale-setup")
    definition = discover_extensions(tmp_path).extensions[0]
    env_dir = tmp_path / "extension-env"
    env_dir.mkdir()
    (env_dir / "metadata.sha256").write_text("old-fingerprint", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(extensions.subprocess, "run", fake_run)

    extensions._ensure_extension_env(definition, env_dir, timeout=2)

    assert calls == [["uv", "venv", "--clear", str(env_dir)]]
    assert (env_dir / "metadata.sha256").read_text(encoding="utf-8") == (
        definition.metadata_fingerprint
    )


def test_run_extension_reports_exception_and_non_dict_result(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_runner(monkeypatch, tmp_path)
    _write_extension(
        tmp_path,
        "boom",
        "def run(input: dict) -> dict:\n    raise RuntimeError('boom')\n",
    )
    boom = discover_extensions(tmp_path).extensions[0]
    assert run_extension(boom, {}, workspace=tmp_path).error == {
        "type": "RuntimeError",
        "message": "boom",
    }

    _write_extension(
        tmp_path,
        "bad-result",
        "def run(input: dict) -> dict:\n    return 'not a dict'\n",
    )
    bad = find_extension_for_slash("/bad-result", tmp_path)
    assert bad is not None
    result = run_extension(bad, {}, workspace=tmp_path)
    assert result.ok is False
    assert result.error and result.error["type"] == "RuntimeError"


def test_find_extension_for_slash_requires_slash_prefix(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "hello")

    assert find_extension_for_slash("hello", tmp_path) is None
    assert find_extension_for_slash("hello can you help", tmp_path) is None
    assert find_extension_for_slash("/hello", tmp_path) is not None


def test_run_extension_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_runner(monkeypatch, tmp_path)
    _write_extension(
        tmp_path,
        "slow",
        "def run(input: dict) -> dict:\n    import time\n    time.sleep(2)\n    return {}\n",
    )
    definition = discover_extensions(tmp_path).extensions[0]

    result = run_extension(definition, {}, workspace=tmp_path, timeout=0.1)

    assert result.ok is False
    assert result.error and result.error["type"] == "timeout"


def test_tool_catalog_with_extensions_exposes_extension_tool(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "custom-tool")

    catalog, diagnostics = tool_catalog_with_extensions(ToolCatalog(), tmp_path)

    assert diagnostics == []
    spec = catalog.get_spec("custom-tool")
    assert spec is not None
    assert spec.description == "Does a thing"
    assert catalog.get_handler("custom-tool") is not None


def test_tool_catalog_with_extensions_preserves_reserved_names_dynamically(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "project-command")

    catalog, diagnostics = tool_catalog_with_extensions(
        ToolCatalog(), tmp_path, reserved_names={"project-command"}
    )

    assert diagnostics
    assert "collides" in diagnostics[0].message
    assert catalog.get_spec("project-command") is None
    assert catalog.get_handler("project-command") is None


def test_tool_catalog_with_extensions_refreshes_callable_reserved_names(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "dynamic-command")
    reserved_names: set[str] = set()

    catalog, diagnostics = tool_catalog_with_extensions(
        ToolCatalog(), tmp_path, reserved_names=lambda: reserved_names
    )

    assert diagnostics == []
    assert catalog.get_spec("dynamic-command") is not None
    reserved_names.add("dynamic-command")
    assert catalog.get_spec("dynamic-command") is None


def test_reserved_slash_extension_names_include_compact(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    names = reserved_slash_extension_names()

    assert "compact" in names


def test_open_runtime_provider_passes_command_reservations(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_command(tmp_path, "project-command")
    captured: dict[str, object] = {}

    class _McpPoolStub:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def __enter__(self) -> _McpPoolStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def to_tool_catalog(self, *, directory_key: str | None = None) -> ToolCatalog:
            del directory_key
            return ToolCatalog().merged(
                [
                    ToolCatalogEntry(
                        spec=ToolSpec(
                            name="mcp-foo",
                            description="MCP foo tool.",
                            parameters_schema={"type": "object"},
                        ),
                        handler=_empty_tool_handler,
                    )
                ],
                source_label="MCP",
            )

    class _ProviderStub:
        def __enter__(self) -> _ProviderStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def _tool_catalog_with_extensions(
        base: ToolCatalog,
        workspace: Path,
        *,
        reserved_names: object = None,
    ) -> tuple[ToolCatalog, list[object]]:
        del workspace
        captured["reserved_names"] = reserved_names
        return base, []

    monkeypatch.setattr("pbi_agent.mcp.McpServerPool", _McpPoolStub)
    monkeypatch.setattr(
        "pbi_agent.agent.session.tool_catalog_with_extensions",
        _tool_catalog_with_extensions,
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: _ProviderStub(),
    )

    with session_module._open_runtime_provider(
        Settings(api_key="test-key", provider="openai")
    ):
        reserved_names = captured["reserved_names"]
        assert callable(reserved_names)
        get_reserved_names = cast(Callable[[], set[str]], reserved_names)
        assert {"compact", "skills", "project-command", "mcp-foo"} <= (
            get_reserved_names()
        )


def test_open_runtime_provider_binds_command_reservations_to_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    monkeypatch.chdir(workspace_a)
    _write_command(workspace_a, "from-a")
    _write_command(workspace_b, "from-b")
    captured: dict[str, object] = {}

    class _McpPoolStub:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def __enter__(self) -> _McpPoolStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def to_tool_catalog(self, *, directory_key: str | None = None) -> ToolCatalog:
            del directory_key
            return ToolCatalog()

    class _ProviderStub:
        def __enter__(self) -> _ProviderStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def _tool_catalog_with_extensions(
        base: ToolCatalog,
        workspace: Path,
        *,
        reserved_names: object = None,
    ) -> tuple[ToolCatalog, list[object]]:
        captured["workspace"] = workspace
        captured["reserved_names"] = reserved_names
        return base, []

    monkeypatch.setattr("pbi_agent.mcp.McpServerPool", _McpPoolStub)
    monkeypatch.setattr(
        "pbi_agent.agent.session.tool_catalog_with_extensions",
        _tool_catalog_with_extensions,
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: _ProviderStub(),
    )

    with session_module._open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        workspace_root=workspace_b,
    ):
        assert captured["workspace"] == workspace_b.resolve()
        reserved_names = captured["reserved_names"]
        assert callable(reserved_names)
        get_reserved_names = cast(Callable[[], set[str]], reserved_names)
        reserved = get_reserved_names()
        assert "from-b" in reserved
        assert "from-a" not in reserved


def test_reserved_slash_extension_names_include_active_mcp_tools(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "mcp-foo")

    class _McpPoolStub:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def __enter__(self) -> _McpPoolStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def to_tool_catalog(self, *, directory_key: str | None = None) -> ToolCatalog:
            del directory_key
            return ToolCatalog().merged(
                [
                    ToolCatalogEntry(
                        spec=ToolSpec(
                            name="mcp-foo",
                            description="MCP foo tool.",
                            parameters_schema={"type": "object"},
                        ),
                        handler=_empty_tool_handler,
                    )
                ],
                source_label="MCP",
            )

    class _ProviderStub:
        def __enter__(self) -> _ProviderStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr("pbi_agent.mcp.McpServerPool", _McpPoolStub)
    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: _ProviderStub(),
    )

    with session_module._open_runtime_provider(
        Settings(api_key="test-key", provider="openai")
    ):
        reserved = reserved_slash_extension_names()
        assert "mcp-foo" in reserved
        assert (
            find_extension_for_slash(
                "/mcp-foo",
                tmp_path,
                reserved_names=reserved,
            )
            is None
        )


def test_extensions_markdown_lists_extensions_and_diagnostics(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "ok")
    _write_extension(tmp_path, "shell")
    (tmp_path / ".agents" / "extensions" / "bad.py").write_text("", encoding="utf-8")

    markdown = format_extensions_markdown(tmp_path)

    assert "`/ok`" in markdown
    assert "`/shell`" not in markdown
    assert "collides" in markdown
    assert "Diagnostics" in markdown


def test_extensions_markdown_reserves_command_names(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "skills")

    markdown = format_extensions_markdown(tmp_path, reserved_names={"skills"})

    assert "`/skills`" not in markdown
    assert "collides" in markdown


def test_extension_handler_marks_failed_runs_as_tool_errors(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "boom")
    definition = discover_extensions(tmp_path).extensions[0]
    monkeypatch.setattr(
        extensions,
        "run_extension",
        lambda definition, arguments, *, workspace: extensions.ExtensionRunResult(
            ok=False,
            error={"type": "boom", "message": "failed"},
        ),
    )

    output = extensions.ExtensionHandler(definition, tmp_path)({}, ToolContext())

    assert output.is_error is True
    assert isinstance(output.result, dict)
    assert output.result["ok"] is False


def test_run_extension_reports_setup_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "deps")
    definition = discover_extensions(tmp_path).extensions[0]

    def timeout_setup(
        definition, env_dir, *, timeout: float = extensions.EXTENSION_TIMEOUT_SECONDS
    ) -> None:
        raise subprocess.TimeoutExpired(cmd=["uv", "pip", "install"], timeout=timeout)

    monkeypatch.setattr(extensions, "_ensure_extension_env", timeout_setup)

    result = run_extension(definition, {}, workspace=tmp_path, timeout=0.1)

    assert result.ok is False
    assert result.error == {
        "type": "setup_failed",
        "message": "Extension setup timed out after 0.1s.",
    }


def test_slash_search_includes_extensions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "custom-tool")

    class Manager(CatalogsMixin):
        _workspace_root = tmp_path

    items = Manager().search_slash_commands("custom", limit=5)

    assert {
        "name": "/custom-tool",
        "description": "Does a thing",
        "kind": "extension",
    } in items


def test_slash_search_excludes_extensions_that_collide_with_builtin_tools(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "shell")

    class Manager(CatalogsMixin):
        _workspace_root = tmp_path

    items = Manager().search_slash_commands("shell", limit=5)

    assert all(item["name"] != "/shell" for item in items)


def test_slash_search_excludes_extensions_that_collide_with_active_mcp_tools(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_extension(tmp_path, "mcp-foo")

    class _McpPoolStub:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def __enter__(self) -> _McpPoolStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def to_tool_catalog(self, *, directory_key: str | None = None) -> ToolCatalog:
            return ToolCatalog().merged(
                [
                    ToolCatalogEntry(
                        spec=ToolSpec(
                            name="mcp-foo",
                            description="MCP foo tool.",
                            parameters_schema={"type": "object"},
                        ),
                        handler=_empty_tool_handler,
                    )
                ],
                source_label="MCP",
            )

    class _ProviderStub:
        def __enter__(self) -> _ProviderStub:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    class Manager(CatalogsMixin):
        _workspace_root = tmp_path

    monkeypatch.setattr("pbi_agent.mcp.McpServerPool", _McpPoolStub)
    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: _ProviderStub(),
    )

    with session_module._open_runtime_provider(
        Settings(api_key="test-key", provider="openai")
    ):
        items = Manager().search_slash_commands("mcp", limit=5)

    assert all(item["name"] != "/mcp-foo" for item in items)
