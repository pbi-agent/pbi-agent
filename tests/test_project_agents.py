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

import pbi_agent.agents.project_installer as project_installer
from pbi_agent.agents.project_catalog import (
    discover_installed_project_agents,
    render_installed_project_agents,
)
from pbi_agent.agents.project_installer import (
    DEFAULT_AGENTS_SOURCE,
    GitHubAgentSource,
    LocalAgentSource,
    ProjectAgentInstallError,
    install_project_agent,
    list_remote_project_agents,
    parse_github_agent_source,
    parse_project_agent_source,
    render_remote_agent_listing,
    resolve_default_agents_source,
)


def _write_agent(root: Path, name: str, description: str, prompt: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{prompt}\n",
        encoding="utf-8",
    )
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


def test_render_installed_project_agents_lists_table(tmp_path: Path) -> None:
    _write_agent(
        tmp_path / ".agents" / "agents",
        "code-reviewer",
        "Reviews code changes.",
        "You are a code reviewer.",
    )
    output = io.StringIO()

    rc = render_installed_project_agents(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    rendered = output.getvalue()
    assert "Project Agents" in rendered
    assert "code-reviewer" in rendered
    assert "Reviews code changes." in rendered


def test_render_installed_project_agents_shows_empty_state(tmp_path: Path) -> None:
    output = io.StringIO()

    rc = render_installed_project_agents(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    assert "No project agents discovered under" in output.getvalue()


def test_discover_installed_project_agents_is_workspace_scoped(tmp_path: Path) -> None:
    workspace_one = tmp_path / "one"
    workspace_two = tmp_path / "two"
    _write_agent(
        workspace_one / ".agents" / "agents",
        "code-reviewer",
        "First workspace agent.",
        "Prompt one.",
    )
    _write_agent(
        workspace_two / ".agents" / "agents",
        "researcher",
        "Second workspace agent.",
        "Prompt two.",
    )

    discovered = discover_installed_project_agents(workspace=workspace_one)

    assert [agent.name for agent in discovered] == ["code-reviewer"]


def test_default_agents_source_helper_returns_official_catalog() -> None:
    assert DEFAULT_AGENTS_SOURCE == "pbi-agent/agents"
    assert resolve_default_agents_source() == "pbi-agent/agents"


def test_parse_project_agent_source_accepts_local_paths_and_keeps_owner_repo() -> None:
    local_relative = parse_project_agent_source("./agents")
    local_current = parse_project_agent_source(".")
    local_windows = parse_project_agent_source(r"C:\agents\repo")
    github = parse_project_agent_source("owner/repo")

    assert isinstance(local_relative, LocalAgentSource)
    assert isinstance(local_current, LocalAgentSource)
    assert isinstance(local_windows, LocalAgentSource)
    assert isinstance(github, GitHubAgentSource)
    assert github.owner_repo == "owner/repo"


def test_parse_github_agent_source_parses_repo_and_tree_urls() -> None:
    repo_source = parse_github_agent_source("https://github.com/owner/repo")
    tree_source = parse_github_agent_source(
        "https://github.com/owner/repo/tree/feature/foo/agents"
    )

    assert repo_source.owner_repo == "owner/repo"
    assert repo_source.tree_parts is None
    assert tree_source.owner_repo == "owner/repo"
    assert tree_source.tree_parts == ("feature", "foo", "agents")


def test_list_and_install_local_single_agent_file_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    agent_file = _write_agent(
        source_root,
        "code-reviewer",
        "Reviews code changes.",
        "You are a code reviewer.",
    )

    listing = list_remote_project_agents(str(agent_file))
    output = io.StringIO()
    render_remote_agent_listing(
        listing,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    result = install_project_agent(str(agent_file), workspace=tmp_path / "workspace")

    assert listing.ref is None
    assert [candidate.agent_name for candidate in listing.candidates] == [
        "code-reviewer"
    ]
    assert "Available Agents" in output.getvalue()
    assert result.agent_name == "code-reviewer"
    assert result.ref is None
    assert (
        tmp_path / "workspace" / ".agents" / "agents" / "code-reviewer.md"
    ).is_file()


def test_local_multi_agent_source_lists_and_requires_agent_for_install(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _write_agent(source_root / "agents", "alpha", "Alpha agent.", "Prompt A.")
    _write_agent(source_root / "agents", "beta", "Beta agent.", "Prompt B.")

    listing = list_remote_project_agents(str(source_root))

    assert [candidate.agent_name for candidate in listing.candidates] == [
        "alpha",
        "beta",
    ]
    with pytest.raises(
        ProjectAgentInstallError,
        match=r"--list or --agent <name>",
    ):
        install_project_agent(str(source_root), workspace=tmp_path / "workspace")


def test_local_source_ignores_internal_dot_agents_agents(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_agent(source_root / "agents", "alpha", "Alpha agent.", "Prompt A.")
    _write_agent(
        source_root / ".agents" / "agents",
        "internal-only",
        "Internal agent.",
        "Internal prompt.",
    )

    listing = list_remote_project_agents(str(source_root))

    assert [candidate.agent_name for candidate in listing.candidates] == ["alpha"]
    assert all(
        candidate.subpath != ".agents/agents/internal-only.md"
        for candidate in listing.candidates
    )


def test_explicit_local_agents_directory_is_supported(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_agent(
        source_root / ".agents" / "agents",
        "code-reviewer",
        "Reviews code changes.",
        "You are a code reviewer.",
    )

    listing = list_remote_project_agents(str(source_root / ".agents" / "agents"))

    assert [candidate.agent_name for candidate in listing.candidates] == [
        "code-reviewer"
    ]
    assert listing.candidates[0].subpath == "code-reviewer.md"


def test_install_project_agent_attaches_bearer_auth_when_token_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/agents/code-reviewer.md": (
                "---\nname: code-reviewer\ndescription: Reviews code changes.\n---\n\n"
                "You are a code reviewer.\n"
            ),
        }
    )
    seen_requests = _install_fake_github(monkeypatch, archive_bytes=archive_bytes)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    install_project_agent("owner/repo", workspace=tmp_path)

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
        git_calls.append(
            (tuple(args), None if env is None else env.get("GIT_TERMINAL_PROMPT"))
        )
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:3] == ["git", "clone", "--depth"]:
            destination = Path(args[-1])
            (destination / "agents").mkdir(parents=True, exist_ok=True)
            _write_agent(
                destination / "agents",
                "code-reviewer",
                "Reviews code changes.",
                "You are a code reviewer.",
            )
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = install_project_agent("owner/repo", workspace=tmp_path)

    assert result.agent_name == "code-reviewer"
    assert result.ref is None
    assert (tmp_path / ".agents" / "agents" / "code-reviewer.md").is_file()
    clone_call = next(args for args, _ in git_calls if args[:2] == ("git", "clone"))
    assert "https://github.com/owner/repo.git" in clone_call
    assert "--branch" not in clone_call
    assert any(prompt == "0" for _, prompt in git_calls if _[:2] == ("git", "clone"))


def test_created_temp_directories_are_cleaned_up_after_list_and_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    _write_agent(
        source_root / "agents",
        "code-reviewer",
        "Reviews code changes.",
        "You are a code reviewer.",
    )
    created_roots = _track_temporary_directories(monkeypatch)

    listing = list_remote_project_agents(str(source_root))
    result = install_project_agent(
        str(source_root),
        agent_name="code-reviewer",
        workspace=tmp_path / "workspace",
    )

    assert listing.candidates[0].agent_name == "code-reviewer"
    assert result.install_path.exists()
    assert created_roots
    assert all(not path.exists() for path in created_roots)


def test_install_force_replaces_existing_agent(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_agent(source_root, "code-reviewer", "New desc.", "New prompt.")
    target = _write_agent(
        tmp_path / "workspace" / ".agents" / "agents",
        "code-reviewer",
        "Old desc.",
        "Old prompt.",
    )

    result = install_project_agent(
        str(source_root / "code-reviewer.md"),
        workspace=tmp_path / "workspace",
        force=True,
    )

    assert result.install_path == target
    assert "New desc." in target.read_text(encoding="utf-8")


def test_install_without_force_rejects_existing_agent(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_agent(source_root, "code-reviewer", "New desc.", "New prompt.")
    _write_agent(
        tmp_path / "workspace" / ".agents" / "agents",
        "code-reviewer",
        "Old desc.",
        "Old prompt.",
    )

    with pytest.raises(ProjectAgentInstallError, match="already installed"):
        install_project_agent(
            str(source_root / "code-reviewer.md"),
            workspace=tmp_path / "workspace",
        )


@pytest.mark.parametrize(
    "declared_name",
    ["../escaped", "nested/reviewer", r"nested\\reviewer", "/tmp/x", ".", ".."],
)
def test_install_rejects_agent_names_that_are_not_single_path_segments(
    tmp_path: Path,
    declared_name: str,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    agent_file = source_root / "candidate.md"
    agent_file.write_text(
        (
            f"---\nname: {declared_name}\n"
            "description: Reviews code changes.\n---\n\n"
            "You are a code reviewer.\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ProjectAgentInstallError,
        match="single path segment|must not be empty",
    ):
        install_project_agent(str(agent_file), workspace=tmp_path / "workspace")

    assert not (tmp_path / "workspace" / ".agents" / "agents").exists()


def test_invalid_agent_source_raises_clean_error(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    (source_root / "agents").mkdir(parents=True)
    (source_root / "agents" / "broken.md").write_text(
        "no frontmatter\n", encoding="utf-8"
    )

    with pytest.raises(ProjectAgentInstallError, match="No valid agents found"):
        list_remote_project_agents(str(source_root))
