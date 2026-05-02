from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from pathlib import Path

import pytest
from rich.console import Console

import pbi_agent.commands.project_installer as project_installer
from pbi_agent.commands.project_catalog import (
    discover_installed_project_commands,
    render_installed_project_commands,
)
from pbi_agent.commands.project_installer import (
    DEFAULT_COMMANDS_SOURCE,
    GitHubCommandSource,
    LocalCommandSource,
    ProjectCommandInstallError,
    install_project_command,
    list_remote_project_commands,
    parse_github_command_source,
    parse_project_command_source,
    render_remote_command_listing,
    resolve_default_commands_source,
)


def _write_command(root: Path, name: str, content: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _make_zip_archive(members: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in members.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _install_fake_github(
    monkeypatch: pytest.MonkeyPatch,
    *,
    owner: str = "owner",
    repo: str = "repo",
    ref: str = "main",
    archive_bytes: bytes | None = None,
    include_default_branch_lookup: bool = True,
    extra_responses: dict[str, bytes] | None = None,
    http_errors: dict[str, int] | None = None,
) -> list[urllib.request.Request]:
    seen_requests: list[urllib.request.Request] = []
    responses: dict[str, bytes] = {}
    if archive_bytes is not None:
        responses[
            f"https://api.github.com/repos/{owner}/{repo}/zipball/"
            f"{urllib.parse.quote(ref, safe='')}"
        ] = archive_bytes
    if include_default_branch_lookup:
        responses[f"https://api.github.com/repos/{owner}/{repo}"] = json.dumps(
            {"default_branch": ref}
        ).encode("utf-8")
    if extra_responses:
        responses.update(extra_responses)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float = 0.0
    ) -> _FakeResponse:
        seen_requests.append(request)
        if http_errors and request.full_url in http_errors:
            raise urllib.error.HTTPError(
                request.full_url,
                http_errors[request.full_url],
                "mocked error",
                hdrs=None,
                fp=None,
            )
        try:
            return _FakeResponse(responses[request.full_url])
        except KeyError as exc:
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "mocked error",
                hdrs=None,
                fp=None,
            ) from exc

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen_requests


def _track_temporary_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Path]:
    created_roots: list[Path] = []

    class _TrackingTemporaryDirectory:
        def __init__(self, *, prefix: str = "tmp") -> None:
            self.path = Path(tempfile.mkdtemp(prefix=prefix))
            created_roots.append(self.path)

        def __enter__(self) -> str:
            return str(self.path)

        def __exit__(self, exc_type, exc, tb) -> bool:
            shutil.rmtree(self.path, ignore_errors=True)
            return False

    monkeypatch.setattr(
        project_installer,
        "TemporaryDirectory",
        _TrackingTemporaryDirectory,
    )
    return created_roots


def test_render_installed_project_commands_lists_table(tmp_path: Path) -> None:
    _write_command(
        tmp_path / ".agents" / "commands",
        "execute",
        "# Execute\n\nRun the task end-to-end.\n",
    )
    output = io.StringIO()

    rc = render_installed_project_commands(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    rendered = output.getvalue()
    assert "Project Commands" in rendered
    assert "/execute" in rendered
    assert "Execute" in rendered


def test_render_installed_project_commands_shows_empty_state(tmp_path: Path) -> None:
    output = io.StringIO()

    rc = render_installed_project_commands(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    assert "No project commands discovered under" in output.getvalue()


def test_discover_installed_project_commands_is_workspace_scoped(
    tmp_path: Path,
) -> None:
    workspace_one = tmp_path / "one"
    workspace_two = tmp_path / "two"
    _write_command(
        workspace_one / ".agents" / "commands",
        "execute",
        "# Execute\n\nFirst workspace command.\n",
    )
    _write_command(
        workspace_two / ".agents" / "commands",
        "review",
        "# Review\n\nSecond workspace command.\n",
    )

    discovered = discover_installed_project_commands(workspace=workspace_one)

    assert [command.id for command in discovered] == ["execute"]


def test_default_commands_source_helper_returns_official_catalog() -> None:
    assert DEFAULT_COMMANDS_SOURCE == "pbi-agent/commands"
    assert resolve_default_commands_source() == "pbi-agent/commands"


def test_parse_project_command_source_accepts_local_paths_and_keeps_owner_repo() -> (
    None
):
    local_relative = parse_project_command_source("./commands")
    local_current = parse_project_command_source(".")
    local_windows = parse_project_command_source(r"C:\commands\repo")
    github = parse_project_command_source("owner/repo")

    assert isinstance(local_relative, LocalCommandSource)
    assert isinstance(local_current, LocalCommandSource)
    assert isinstance(local_windows, LocalCommandSource)
    assert isinstance(github, GitHubCommandSource)
    assert github.owner_repo == "owner/repo"


def test_parse_github_command_source_parses_repo_and_tree_urls() -> None:
    repo_source = parse_github_command_source("https://github.com/owner/repo")
    tree_source = parse_github_command_source(
        "https://github.com/owner/repo/tree/feature/foo/commands"
    )

    assert repo_source.owner_repo == "owner/repo"
    assert repo_source.tree_parts is None
    assert tree_source.owner_repo == "owner/repo"
    assert tree_source.tree_parts == ("feature", "foo", "commands")


def test_list_and_install_local_single_command_file_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    command_file = _write_command(
        source_root,
        "execute",
        "# Execute\n\nRun the task end-to-end.\n",
    )

    listing = list_remote_project_commands(str(command_file))
    output = io.StringIO()
    render_remote_command_listing(
        listing,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    result = install_project_command(
        str(command_file), workspace=tmp_path / "workspace"
    )

    assert listing.ref is None
    assert [candidate.command_id for candidate in listing.candidates] == ["execute"]
    assert "Available Commands" in output.getvalue()
    assert result.command_id == "execute"
    assert result.ref is None
    assert (tmp_path / "workspace" / ".agents" / "commands" / "execute.md").is_file()


def test_local_multi_command_source_lists_and_requires_command_for_install(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _write_command(source_root / "commands", "alpha", "# Alpha\n\nAlpha command.\n")
    _write_command(source_root / "commands", "beta", "# Beta\n\nBeta command.\n")

    listing = list_remote_project_commands(str(source_root))

    assert [candidate.command_id for candidate in listing.candidates] == [
        "alpha",
        "beta",
    ]
    with pytest.raises(
        ProjectCommandInstallError,
        match=r"--list or --command <name>",
    ):
        install_project_command(str(source_root), workspace=tmp_path / "workspace")


def test_local_source_ignores_internal_dot_agents_commands(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_command(source_root / "commands", "alpha", "# Alpha\n\nAlpha command.\n")
    _write_command(
        source_root / ".agents" / "commands",
        "internal-only",
        "# Internal\n\nInternal command.\n",
    )

    listing = list_remote_project_commands(str(source_root))

    assert [candidate.command_id for candidate in listing.candidates] == ["alpha"]
    assert all(
        candidate.subpath != ".agents/commands/internal-only.md"
        for candidate in listing.candidates
    )


def test_explicit_local_agents_commands_directory_is_supported(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_command(
        source_root / ".agents" / "commands",
        "execute",
        "# Execute\n\nRun the task end-to-end.\n",
    )

    listing = list_remote_project_commands(str(source_root / ".agents" / "commands"))

    assert [candidate.command_id for candidate in listing.candidates] == ["execute"]
    assert listing.candidates[0].subpath == "execute.md"


def test_install_project_command_attaches_bearer_auth_when_token_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/commands/execute.md": "# Execute\n\nRun the task end-to-end.\n",
        }
    )
    seen_requests = _install_fake_github(monkeypatch, archive_bytes=archive_bytes)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    install_project_command("owner/repo", workspace=tmp_path)

    assert seen_requests[0].get_header("Authorization") == "Bearer secret-token"
    assert seen_requests[1].get_header("Authorization") == "Bearer secret-token"


def test_private_repo_404_falls_back_to_git_and_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_github(
        monkeypatch,
        archive_bytes=None,
        http_errors={"https://api.github.com/repos/owner/repo": 404},
    )
    git_calls: list[tuple[tuple[str, ...], str | None]] = []

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        git_calls.append(
            (tuple(args), None if env is None else env.get("GIT_TERMINAL_PROMPT"))
        )
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:3] == ["git", "clone", "--depth"]:
            destination = Path(args[-1])
            (destination / "commands").mkdir(parents=True, exist_ok=True)
            (destination / "commands" / "execute.md").write_text(
                "# Execute\n\nRun the task end-to-end.\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = install_project_command("owner/repo", workspace=tmp_path)

    assert result.command_id == "execute"
    assert result.ref is None
    assert (tmp_path / ".agents" / "commands" / "execute.md").is_file()
    clone_call = next(args for args, _ in git_calls if args[:2] == ("git", "clone"))
    assert "https://github.com/owner/repo.git" in clone_call
    assert "--branch" not in clone_call
    assert any(prompt == "0" for _, prompt in git_calls if _[:2] == ("git", "clone"))


def test_remote_listing_ignores_internal_dot_agents_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/commands/execute.md": "# Execute\n\nPublic command.\n",
            "repo-main/.agents/commands/internal.md": "# Internal\n\nInternal command.\n",
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    listing = list_remote_project_commands("owner/repo")

    assert [candidate.command_id for candidate in listing.candidates] == ["execute"]
    assert all(
        candidate.subpath != ".agents/commands/internal.md"
        for candidate in listing.candidates
    )


def test_remote_tree_url_can_target_agents_commands_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/.agents/commands/execute.md": "# Execute\n\nInternal command.\n",
        }
    )
    _install_fake_github(
        monkeypatch,
        archive_bytes=archive_bytes,
        include_default_branch_lookup=False,
        extra_responses={
            "https://api.github.com/repos/owner/repo/git/matching-refs/heads/main": json.dumps(
                [{"ref": "refs/heads/main"}]
            ).encode("utf-8"),
        },
    )

    listing = list_remote_project_commands(
        "https://github.com/owner/repo/tree/main/.agents/commands"
    )

    assert [candidate.command_id for candidate in listing.candidates] == ["execute"]


def test_command_installer_cleans_up_temporary_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/commands/execute.md": "# Execute\n\nRun the task end-to-end.\n",
        }
    )
    created_roots = _track_temporary_directories(monkeypatch)
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    list_remote_project_commands("owner/repo")
    install_project_command("owner/repo", workspace=tmp_path)

    assert created_roots
    assert all(not path.exists() for path in created_roots)
