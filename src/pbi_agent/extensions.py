from __future__ import annotations

import hashlib
import json
import os
import subprocess
import textwrap
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pbi_agent.config import slugify
from pbi_agent.tools.catalog import ToolCatalog, ToolCatalogEntry
from pbi_agent.tools.output import bound_output, decode_output
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec
from pbi_agent.workspace_context import current_workspace_context

EXTENSIONS_DIR = Path(".agents") / "extensions"
EXTENSION_CACHE_ROOT = Path.home() / ".pbi-agent" / "extensions"
EXTENSION_TIMEOUT_SECONDS = 120.0
_RUNNER_TIMEOUT_SECONDS = EXTENSION_TIMEOUT_SECONDS + 5.0
_MAX_LOG_CHARS = 4000
ExtensionReservedNames = set[str] | Callable[[], set[str]]


@dataclass(slots=True, frozen=True)
class ExtensionDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    dependencies: tuple[str, ...]
    path: Path
    metadata_fingerprint: str


@dataclass(slots=True, frozen=True)
class ExtensionDiagnostic:
    path: Path | None
    message: str


@dataclass(slots=True)
class ExtensionDiscovery:
    extensions: list[ExtensionDefinition] = field(default_factory=list)
    diagnostics: list[ExtensionDiagnostic] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ExtensionRunResult:
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class ExtensionHandler:
    def __init__(self, definition: ExtensionDefinition, workspace: Path) -> None:
        self._definition = definition
        self._workspace = workspace

    def __call__(self, arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
        del context
        result = run_extension(self._definition, arguments, workspace=self._workspace)
        payload: dict[str, Any] = {
            "ok": result.ok,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.stdout_truncated:
            payload["stdout_truncated"] = True
        if result.stderr_truncated:
            payload["stderr_truncated"] = True
        if result.ok:
            payload["result"] = result.result or {}
        else:
            payload["error"] = result.error or {
                "type": "extension_failed",
                "message": "Extension failed.",
            }
        return ToolOutput(result=payload, is_error=not result.ok)


class ExtensionToolCatalog(ToolCatalog):
    def __init__(
        self,
        base: ToolCatalog,
        workspace: Path,
        reserved_names: ExtensionReservedNames | None = None,
    ) -> None:
        self._base = base
        self._workspace = workspace.resolve()
        self._reserved_names = reserved_names

    def names(self) -> list[str]:
        return self._current().names()

    def sub_agent_type_values(self) -> tuple[str, ...]:
        return self._base.sub_agent_type_values()

    def is_sub_agent_type_visible(self, agent_type: str) -> bool:
        return self._base.is_sub_agent_type_visible(agent_type)

    def with_sub_agent_visibility(
        self,
        workspace: Path | None = None,
        *,
        directory_key: str | None = None,
        visible_sub_agent_names: tuple[str, ...] | None = None,
    ) -> ToolCatalog:
        return ExtensionToolCatalog(
            self._base.with_sub_agent_visibility(
                workspace or self._workspace,
                directory_key=directory_key,
                visible_sub_agent_names=visible_sub_agent_names,
            ),
            self._workspace,
            self._reserved_names,
        )

    def with_spec(
        self,
        spec: ToolSpec,
        *,
        sub_agent_type_values: tuple[str, ...] | None = None,
    ) -> ToolCatalog:
        return ExtensionToolCatalog(
            self._base.with_spec(
                spec,
                sub_agent_type_values=sub_agent_type_values,
            ),
            self._workspace,
            self._reserved_names,
        )

    def get_specs(self, *, excluded_names: set[str] | None = None) -> list[ToolSpec]:
        return self._current().get_specs(excluded_names=excluded_names)

    def get_handler(self, name: str):
        return self._current().get_handler(name)

    def get_spec(self, name: str) -> ToolSpec | None:
        return self._current().get_spec(name)

    def get_openai_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._current().get_openai_tool_definitions(
            excluded_names=excluded_names
        )

    def get_anthropic_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._current().get_anthropic_tool_definitions(
            excluded_names=excluded_names
        )

    def get_openai_chat_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._current().get_openai_chat_tool_definitions(
            excluded_names=excluded_names
        )

    def _current(self) -> ToolCatalog:
        entries, _diagnostics = extension_tool_entries(
            self._workspace,
            reserved_names=_resolve_reserved_names(self._reserved_names)
            | set(self._base.names()),
        )
        return self._base.merged(entries, source_label="extension")


def discover_extensions(
    workspace: Path | None = None,
    *,
    reserved_names: set[str] | None = None,
) -> ExtensionDiscovery:
    root = (workspace or Path.cwd()).resolve()
    extension_dir = root / EXTENSIONS_DIR
    discovery = ExtensionDiscovery()
    if not extension_dir.is_dir():
        return discovery

    reserved = set(reserved_names or set())
    seen: set[str] = set()
    for path in sorted(extension_dir.glob("*.py")):
        try:
            definition = _load_extension(path)
        except Exception as exc:
            discovery.diagnostics.append(
                ExtensionDiagnostic(path=path, message=f"Invalid extension: {exc}")
            )
            continue
        if definition.name in reserved:
            discovery.diagnostics.append(
                ExtensionDiagnostic(
                    path=path,
                    message=(
                        f"Skipping extension {definition.name!r}: name collides "
                        "with an existing command or tool."
                    ),
                )
            )
            continue
        if definition.name in seen:
            discovery.diagnostics.append(
                ExtensionDiagnostic(
                    path=path,
                    message=f"Skipping extension {definition.name!r}: duplicate name.",
                )
            )
            continue
        seen.add(definition.name)
        discovery.extensions.append(definition)
    return discovery


def extension_tool_entries(
    workspace: Path | None = None,
    *,
    reserved_names: set[str] | None = None,
) -> tuple[list[ToolCatalogEntry], list[ExtensionDiagnostic]]:
    root = (workspace or Path.cwd()).resolve()
    discovery = discover_extensions(root, reserved_names=reserved_names)
    entries = [
        ToolCatalogEntry(
            spec=ToolSpec(
                name=definition.name,
                description=definition.description,
                parameters_schema=definition.input_schema,
            ),
            handler=ExtensionHandler(definition, root),
        )
        for definition in discovery.extensions
    ]
    return entries, discovery.diagnostics


def tool_catalog_with_extensions(
    base: ToolCatalog,
    workspace: Path | None = None,
    *,
    reserved_names: ExtensionReservedNames | None = None,
) -> tuple[ToolCatalog, list[ExtensionDiagnostic]]:
    reserved = _resolve_reserved_names(reserved_names) | set(base.names())
    _entries, diagnostics = extension_tool_entries(workspace, reserved_names=reserved)
    root = (workspace or Path.cwd()).resolve()
    return ExtensionToolCatalog(base, root, reserved_names), diagnostics


def _resolve_reserved_names(
    reserved_names: ExtensionReservedNames | None,
) -> set[str]:
    if reserved_names is None:
        return set()
    if callable(reserved_names):
        return set(reserved_names())
    return set(reserved_names)


def find_extension_for_slash(
    command: str,
    workspace: Path | None = None,
    *,
    reserved_names: set[str] | None = None,
) -> ExtensionDefinition | None:
    stripped = command.strip()
    if not stripped.startswith("/"):
        return None
    normalized = stripped.lstrip("/").lower()
    if not normalized:
        return None
    discovery = discover_extensions(workspace, reserved_names=reserved_names)
    for definition in discovery.extensions:
        if definition.name == normalized:
            return definition
    return None


def format_extensions_markdown(
    workspace: Path | None = None,
    *,
    reserved_names: set[str] | None = None,
) -> str:
    reserved = set(reserved_names or set()) | set(
        ToolCatalog.from_builtin_registry().names()
    )
    discovery = discover_extensions(workspace, reserved_names=reserved)
    lines = ["# Extensions"]
    if discovery.extensions:
        lines.append("")
        for definition in discovery.extensions:
            rel = _display_path(definition.path, workspace)
            lines.append(f"- `/{definition.name}` — {definition.description} ({rel})")
    else:
        lines.append("")
        lines.append("No extensions found in `.agents/extensions/*.py`.")
    if discovery.diagnostics:
        lines.append("")
        lines.append("## Diagnostics")
        for diagnostic in discovery.diagnostics:
            prefix = (
                _display_path(diagnostic.path, workspace) if diagnostic.path else ""
            )
            lines.append(
                f"- {prefix}: {diagnostic.message}"
                if prefix
                else f"- {diagnostic.message}"
            )
    return "\n".join(lines)


def run_extension(
    definition: ExtensionDefinition,
    input_payload: dict[str, Any],
    *,
    workspace: Path | None = None,
    timeout: float = EXTENSION_TIMEOUT_SECONDS,
) -> ExtensionRunResult:
    root = (workspace or Path.cwd()).resolve()
    env_dir = _extension_env_dir(definition)
    try:
        try:
            _ensure_extension_env(definition, env_dir, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ExtensionRunResult(
                ok=False,
                error={
                    "type": "setup_failed",
                    "message": f"Extension setup timed out after {timeout:g}s.",
                },
            )
        runner = _write_runner_shim(env_dir)
        process = subprocess.run(
            [
                str(_python_executable(env_dir)),
                str(runner),
                str(definition.path),
                json.dumps(input_payload),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = bound_output(
            decode_output(exc.stdout), limit=_MAX_LOG_CHARS
        )
        stderr, stderr_truncated = bound_output(
            decode_output(exc.stderr), limit=_MAX_LOG_CHARS
        )
        return ExtensionRunResult(
            ok=False,
            error={
                "type": "timeout",
                "message": f"Extension timed out after {timeout:g}s.",
            },
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    except Exception as exc:
        return ExtensionRunResult(
            ok=False,
            error={"type": "setup_failed", "message": str(exc)},
        )

    stdout, stdout_truncated = bound_output(process.stdout, limit=_MAX_LOG_CHARS)
    stderr, stderr_truncated = bound_output(process.stderr, limit=_MAX_LOG_CHARS)
    try:
        envelope = json.loads(process.stdout or "{}")
    except json.JSONDecodeError:
        return ExtensionRunResult(
            ok=False,
            error={
                "type": "invalid_output",
                "message": "Extension runner returned non-JSON output.",
            },
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    if not isinstance(envelope, dict):
        return ExtensionRunResult(
            ok=False,
            error={
                "type": "extension_failed",
                "message": f"Extension process exited with status {process.returncode}.",
            },
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    raw_logs = envelope.get("logs")
    logs: dict[str, Any] = raw_logs if isinstance(raw_logs, dict) else {}
    raw_logs_truncated = envelope.get("logs_truncated")
    logs_truncated: dict[str, Any] = (
        raw_logs_truncated if isinstance(raw_logs_truncated, dict) else {}
    )
    captured_stdout, captured_stdout_truncated = bound_output(
        str(logs.get("stdout") or ""), limit=_MAX_LOG_CHARS
    )
    captured_stderr, captured_stderr_truncated = bound_output(
        str(logs.get("stderr") or ""), limit=_MAX_LOG_CHARS
    )
    captured_stdout_truncated = (
        captured_stdout_truncated or logs_truncated.get("stdout") is True
    )
    captured_stderr_truncated = (
        captured_stderr_truncated or logs_truncated.get("stderr") is True
    )
    if envelope.get("ok") is True and isinstance(envelope.get("result"), dict):
        return ExtensionRunResult(
            ok=True,
            result=envelope["result"],
            stdout=captured_stdout,
            stderr=captured_stderr,
            stdout_truncated=captured_stdout_truncated,
            stderr_truncated=captured_stderr_truncated,
        )
    if process.returncode != 0 and "error" not in envelope:
        return ExtensionRunResult(
            ok=False,
            error={
                "type": "extension_failed",
                "message": f"Extension process exited with status {process.returncode}.",
            },
            stdout=captured_stdout,
            stderr=captured_stderr,
            stdout_truncated=captured_stdout_truncated,
            stderr_truncated=captured_stderr_truncated,
        )
    raw_error = envelope.get("error")
    error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
    return ExtensionRunResult(
        ok=False,
        error={
            "type": str(error.get("type") or "extension_failed"),
            "message": str(error.get("message") or "Extension failed."),
        },
        stdout=captured_stdout,
        stderr=captured_stderr,
        stdout_truncated=captured_stdout_truncated,
        stderr_truncated=captured_stderr_truncated,
    )


def _load_extension(path: Path) -> ExtensionDefinition:
    text = path.read_text(encoding="utf-8")
    metadata_text = _extract_pep723_metadata(text)
    metadata = tomllib.loads(metadata_text)
    extension = metadata.get("tool", {}).get("pbi-agent", {}).get("extension")
    if not isinstance(extension, dict):
        raise ValueError("missing [tool.pbi-agent.extension] metadata")
    raw_name = extension.get("name")
    description = extension.get("description")
    input_schema = extension.get("input_schema")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError("extension name is required")
    name = slugify(raw_name)
    if not name:
        raise ValueError("extension name must contain letters or numbers")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("extension description is required")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
        raise ValueError("extension input_schema must be an object schema")
    raw_dependencies = metadata.get("dependencies", [])
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, str) for item in raw_dependencies
    ):
        raise ValueError("dependencies must be a list of strings")
    fingerprint_payload = {
        "dependencies": raw_dependencies,
        "name": name,
        "description": description,
        "input_schema": input_schema,
    }
    return ExtensionDefinition(
        name=name,
        description=description.strip(),
        input_schema=dict(input_schema),
        dependencies=tuple(raw_dependencies),
        path=path.resolve(),
        metadata_fingerprint=hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    )


def _extract_pep723_metadata(text: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "# /// script":
            start = index + 1
            break
    if start is None:
        raise ValueError("missing PEP 723 script metadata block")
    block: list[str] = []
    for line in lines[start:]:
        if line.strip() == "# ///":
            return "\n".join(block)
        if not line.startswith("#"):
            raise ValueError("invalid PEP 723 metadata line")
        block.append(line[1:].lstrip(" "))
    raise ValueError("unterminated PEP 723 script metadata block")


def _extension_env_dir(definition: ExtensionDefinition) -> Path:
    workspace_key = hashlib.sha256(
        current_workspace_context().directory_key.encode("utf-8")
    ).hexdigest()[:16]
    return EXTENSION_CACHE_ROOT / workspace_key / definition.name


def _ensure_extension_env(
    definition: ExtensionDefinition,
    env_dir: Path,
    *,
    timeout: float = EXTENSION_TIMEOUT_SECONDS,
) -> None:
    marker = env_dir / "metadata.sha256"
    if _extension_env_is_current(marker, definition):
        return
    with _ExtensionEnvSetupLock(env_dir, timeout=timeout):
        if _extension_env_is_current(marker, definition):
            return
        venv_command = ["uv", "venv"]
        if env_dir.exists():
            venv_command.append("--clear")
        venv_command.append(str(env_dir))
        subprocess.run(
            venv_command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if definition.dependencies:
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(_python_executable(env_dir)),
                    *definition.dependencies,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        marker.write_text(definition.metadata_fingerprint, encoding="utf-8")


def _extension_env_is_current(marker: Path, definition: ExtensionDefinition) -> bool:
    return (
        marker.exists()
        and marker.read_text(encoding="utf-8") == definition.metadata_fingerprint
    )


class _ExtensionEnvSetupLock:
    def __init__(self, env_dir: Path, *, timeout: float) -> None:
        self._path = env_dir.parent / f".{env_dir.name}.setup.lock"
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> _ExtensionEnvSetupLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(
                        cmd=["extension-env-setup-lock", str(self._path)],
                        timeout=self._timeout,
                    ) from exc
                time.sleep(0.05)

    def __exit__(self, *_: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


def _python_executable(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def _write_runner_shim(env_dir: Path) -> Path:
    runner = env_dir / "pbi_extension_runner.py"
    runner.write_text(_RUNNER_SOURCE, encoding="utf-8")
    return runner


def _display_path(path: Path | None, workspace: Path | None) -> str:
    if path is None:
        return ""
    root = (workspace or Path.cwd()).resolve()
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


_RUNNER_SOURCE = textwrap.dedent(
    r"""
    from __future__ import annotations

    import importlib.util
    import json
    import os
    import sys
    import tempfile
    import traceback
    from pathlib import Path


    MAX_LOG_CHARS = 4000


    def main() -> int:
        script = Path(sys.argv[1])
        payload = json.loads(sys.argv[2])
        stdout_file = tempfile.TemporaryFile(mode="w+b")
        stderr_file = tempfile.TemporaryFile(mode="w+b")
        stdout_fd = os.dup(1)
        stderr_fd = os.dup(2)
        envelope = {}
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(stdout_file.fileno(), 1)
            os.dup2(stderr_file.fileno(), 2)
            try:
                spec = importlib.util.spec_from_file_location("pbi_agent_extension", script)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Unable to load extension module.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                run = getattr(module, "run", None)
                if not callable(run):
                    raise RuntimeError("Extension must define run(input: dict) -> dict.")
                result = run(payload)
                if not isinstance(result, dict):
                    raise RuntimeError("Extension run() must return a dict.")
                envelope = {"ok": True, "result": result}
            except BaseException as exc:
                envelope = {
                    "ok": False,
                    "error": {"type": exc.__class__.__name__, "message": str(exc)},
                    "traceback": traceback.format_exc(),
                }
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(stdout_fd, 1)
                os.dup2(stderr_fd, 2)
            stdout_text, stdout_truncated = _read_temp_text(stdout_file)
            stderr_text, stderr_truncated = _read_temp_text(stderr_file)
            if envelope.get("traceback"):
                stderr_text, traceback_truncated = _bound_text(
                    stderr_text + str(envelope.pop("traceback"))
                )
                stderr_truncated = stderr_truncated or traceback_truncated
            envelope["logs"] = {"stdout": stdout_text, "stderr": stderr_text}
            if stdout_truncated or stderr_truncated:
                envelope["logs_truncated"] = {
                    "stdout": stdout_truncated,
                    "stderr": stderr_truncated,
                }
            print(json.dumps(envelope))
            if envelope.get("ok") is not True:
                return 1
            return 0
        finally:
            os.close(stdout_fd)
            os.close(stderr_fd)
            stdout_file.close()
            stderr_file.close()


    def _read_temp_text(handle) -> tuple[str, bool]:
        handle.flush()
        size = handle.seek(0, os.SEEK_END)
        handle.seek(0)
        if size <= MAX_LOG_CHARS:
            return handle.read().decode("utf-8", errors="replace"), False
        omitted = size - MAX_LOG_CHARS
        marker = f"\n... {omitted} bytes omitted ...\n"
        available = max(0, MAX_LOG_CHARS - len(marker))
        head_size = available // 2 + available % 2
        tail_size = available // 2
        head = handle.read(head_size)
        if tail_size:
            handle.seek(-tail_size, os.SEEK_END)
            tail = handle.read(tail_size)
        else:
            tail = b""
        omitted = size - head_size - tail_size
        marker = f"\n... {omitted} bytes omitted ...\n"
        text = (
            head.decode("utf-8", errors="replace")
            + marker
            + tail.decode("utf-8", errors="replace")
        )
        return text[:MAX_LOG_CHARS], True


    def _bound_text(text: str) -> tuple[str, bool]:
        if len(text) <= MAX_LOG_CHARS:
            return text, False
        omitted = len(text) - MAX_LOG_CHARS
        marker = f"\n... {omitted} chars omitted ...\n"
        available = max(0, MAX_LOG_CHARS - len(marker))
        head = available // 2 + available % 2
        tail = available // 2
        omitted = len(text) - head - tail
        marker = f"\n... {omitted} chars omitted ...\n"
        suffix = text[-tail:] if tail else ""
        return f"{text[:head]}{marker}{suffix}"[:MAX_LOG_CHARS], True


    if __name__ == "__main__":
        raise SystemExit(main())
    """
).lstrip()
