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

import pbi_agent.skills.project_installer as project_installer
from pbi_agent.skills.project_catalog import (
    discover_installed_project_skills,
    render_installed_project_skills,
)
from pbi_agent.skills.project_installer import (
    DEFAULT_SKILLS_SOURCE,
    GitHubSkillSource,
    LocalSkillSource,
    ProjectSkillInstallError,
    install_project_skill,
    list_remote_project_skills,
    parse_github_skill_source,
    parse_project_skill_source,
    render_remote_skill_listing,
    resolve_default_skills_source,
)


def _write_skill(
    root: Path,
    name: str,
    description: str,
    *,
    directory_name: str | None = None,
) -> Path:
    skill_dir = root / (directory_name or name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


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
        except KeyError as exc:  # pragma: no cover - test failure path
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


def test_render_installed_project_skills_lists_table(tmp_path: Path) -> None:
    skill_dir = _write_skill(
        tmp_path / ".agents" / "skills",
        "repo-skill",
        "Repository workflow.",
    )
    output = io.StringIO()

    rc = render_installed_project_skills(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    rendered = output.getvalue()
    assert "Project Skills" in rendered
    assert "repo-skill" in rendered
    assert "Repository workflow." in rendered
    assert "Location" not in rendered
    assert str((skill_dir / "SKILL.md").resolve()) not in rendered


def test_render_installed_project_skills_shows_empty_state(tmp_path: Path) -> None:
    output = io.StringIO()

    rc = render_installed_project_skills(
        workspace=tmp_path,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    assert rc == 0
    assert "No project skills discovered under" in output.getvalue()


def test_discover_installed_project_skills_is_workspace_scoped(tmp_path: Path) -> None:
    workspace_one = tmp_path / "one"
    workspace_two = tmp_path / "two"
    _write_skill(
        workspace_one / ".agents" / "skills",
        "one-skill",
        "First workspace skill.",
    )
    _write_skill(
        workspace_two / ".agents" / "skills",
        "two-skill",
        "Second workspace skill.",
    )

    discovered = discover_installed_project_skills(workspace=workspace_one)

    assert [skill.name for skill in discovered] == ["one-skill"]


def test_default_skills_source_helper_returns_official_catalog() -> None:
    assert DEFAULT_SKILLS_SOURCE == "pbi-agent/skills"
    assert resolve_default_skills_source() == "pbi-agent/skills"


def test_parse_project_skill_source_accepts_local_paths_and_keeps_owner_repo() -> None:
    local_relative = parse_project_skill_source("./skills")
    local_current = parse_project_skill_source(".")
    local_windows = parse_project_skill_source(r"C:\skills\repo")
    github = parse_project_skill_source("owner/repo")

    assert isinstance(local_relative, LocalSkillSource)
    assert isinstance(local_current, LocalSkillSource)
    assert isinstance(local_windows, LocalSkillSource)
    assert isinstance(github, GitHubSkillSource)
    assert github.owner_repo == "owner/repo"


def test_parse_github_skill_source_parses_repo_and_tree_urls() -> None:
    repo_source = parse_github_skill_source("https://github.com/owner/repo")
    tree_source = parse_github_skill_source(
        "https://github.com/owner/repo/tree/feature/foo/skills/bar"
    )

    assert repo_source.owner_repo == "owner/repo"
    assert repo_source.tree_parts is None
    assert tree_source.owner_repo == "owner/repo"
    assert tree_source.tree_parts == ("feature", "foo", "skills", "bar")


def test_list_and_install_local_single_skill_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_root = _write_skill(source_root, "local-skill", "Local workflow.")

    listing = list_remote_project_skills(str(skill_root))
    output = io.StringIO()
    render_remote_skill_listing(
        listing,
        console=Console(file=output, force_terminal=False, color_system=None),
    )

    result = install_project_skill(str(skill_root), workspace=tmp_path / "workspace")

    assert listing.ref is None
    assert [candidate.name for candidate in listing.candidates] == ["local-skill"]
    assert "Available Skills" in output.getvalue()
    assert result.name == "local-skill"
    assert result.ref is None
    assert (
        tmp_path / "workspace" / ".agents" / "skills" / "local-skill" / "SKILL.md"
    ).is_file()


def test_local_multi_skill_source_lists_and_requires_skill_for_install(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _write_skill(source_root / "skills", "alpha", "Alpha skill.")
    _write_skill(source_root / "skills", "beta", "Beta skill.")

    listing = list_remote_project_skills(str(source_root))

    assert [candidate.name for candidate in listing.candidates] == ["alpha", "beta"]
    with pytest.raises(
        ProjectSkillInstallError,
        match=r"--list or --skill <name>",
    ):
        install_project_skill(str(source_root), workspace=tmp_path / "workspace")


def test_local_source_ignores_internal_dot_agents_skills(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_skill(source_root / "skills", "alpha", "Alpha skill.")
    _write_skill(
        source_root / ".agents" / "skills",
        "internal-only",
        "Internal source skill.",
    )

    listing = list_remote_project_skills(str(source_root))

    assert [candidate.name for candidate in listing.candidates] == ["alpha"]
    assert all(
        candidate.subpath != ".agents/skills/internal-only"
        for candidate in listing.candidates
    )


def test_install_project_skill_attaches_bearer_auth_when_token_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/SKILL.md": (
                "---\nname: repo-skill\ndescription: Remote workflow skill.\n---\n\n# Repo\n"
            )
        }
    )
    seen_requests = _install_fake_github(monkeypatch, archive_bytes=archive_bytes)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    install_project_skill("owner/repo", workspace=tmp_path)

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
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "SKILL.md").write_text(
                "---\nname: repo-skill\ndescription: Private skill.\n---\n\n# Repo\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = install_project_skill("owner/repo", workspace=tmp_path)

    assert result.name == "repo-skill"
    assert result.ref is None
    assert (tmp_path / ".agents" / "skills" / "repo-skill" / "SKILL.md").is_file()
    clone_call = next(args for args, _ in git_calls if args[:2] == ("git", "clone"))
    assert "https://github.com/owner/repo.git" in clone_call
    assert "--branch" not in clone_call
    assert any(prompt == "0" for _, prompt in git_calls if _[:2] == ("git", "clone"))


def test_remote_listing_ignores_internal_dot_agents_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/skills/powerbi/SKILL.md": (
                "---\nname: powerbi\ndescription: Public skill.\n---\n\n# PowerBI\n"
            ),
            "repo-main/.agents/skills/create-skill/SKILL.md": (
                "---\nname: create-skill\ndescription: Internal skill.\n---\n\n# Internal\n"
            ),
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    listing = list_remote_project_skills("owner/repo")

    assert [candidate.name for candidate in listing.candidates] == ["powerbi"]
    assert all(
        candidate.subpath != ".agents/skills/create-skill"
        for candidate in listing.candidates
    )


def test_tree_url_with_slashful_ref_works_via_git_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_github(
        monkeypatch,
        include_default_branch_lookup=False,
        http_errors={
            "https://api.github.com/repos/owner/repo/git/matching-refs/heads/feature%2Ffoo%2Fskills%2Fbar": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/tags/feature%2Ffoo%2Fskills%2Fbar": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/heads/feature%2Ffoo%2Fskills": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/tags/feature%2Ffoo%2Fskills": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/heads/feature%2Ffoo": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/tags/feature%2Ffoo": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/heads/feature": 404,
            "https://api.github.com/repos/owner/repo/git/matching-refs/tags/feature": 404,
        },
    )
    git_calls: list[tuple[str, ...]] = []

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        git_calls.append(tuple(args))
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:4] == ["git", "ls-remote", "--heads", "--tags"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "111111\trefs/heads/main\n222222\trefs/heads/feature/foo\n",
                "",
            )
        if args[:3] == ["git", "clone", "--depth"]:
            destination = Path(args[-1])
            destination.mkdir(parents=True, exist_ok=True)
            skill_dir = destination / "skills" / "bar"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: bar\ndescription: Branch skill.\n---\n\n# Bar\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = install_project_skill(
        "https://github.com/owner/repo/tree/feature/foo/skills/bar",
        workspace=tmp_path,
    )

    assert result.ref == "feature/foo"
    assert result.subpath == "skills/bar"
    clone_call = next(args for args in git_calls if args[:2] == ("git", "clone"))
    assert "--branch" in clone_call
    assert "feature/foo" in clone_call


def test_https_auth_failure_retries_ssh_before_surfacing_final_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_github(
        monkeypatch,
        archive_bytes=None,
        http_errors={"https://api.github.com/repos/owner/repo": 404},
    )
    clone_calls: list[tuple[str, ...]] = []

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:3] == ["git", "clone", "--depth"]:
            clone_calls.append(tuple(args))
            if args[-2].startswith("https://github.com/"):
                return subprocess.CompletedProcess(
                    args,
                    128,
                    "",
                    "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
                )
            return subprocess.CompletedProcess(
                args,
                128,
                "",
                "git@github.com: Permission denied (publickey).",
            )
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(
        ProjectSkillInstallError,
        match="Confirm repository access and git/SSH credentials are configured",
    ):
        install_project_skill("owner/repo", workspace=tmp_path)

    assert len(clone_calls) == 2
    assert clone_calls[0][-2] == "https://github.com/owner/repo.git"
    assert clone_calls[1][-2] == "git@github.com:owner/repo.git"


def test_temp_materialization_is_removed_after_successful_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_roots = _track_temporary_directories(monkeypatch)
    archive_bytes = _make_zip_archive(
        {
            "repo-main/SKILL.md": (
                "---\nname: repo-skill\ndescription: Remote workflow skill.\n---\n\n# Repo\n"
            )
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    list_remote_project_skills("owner/repo")

    assert created_roots
    assert all(not root.exists() for root in created_roots)


def test_temp_materialization_is_removed_after_successful_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_roots = _track_temporary_directories(monkeypatch)
    archive_bytes = _make_zip_archive(
        {
            "repo-main/SKILL.md": (
                "---\nname: repo-skill\ndescription: Remote workflow skill.\n---\n\n# Repo\n"
            )
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    install_project_skill("owner/repo", workspace=tmp_path)

    assert created_roots
    assert all(not root.exists() for root in created_roots)


def test_temp_materialization_is_removed_after_archive_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_roots = _track_temporary_directories(monkeypatch)
    _install_fake_github(
        monkeypatch,
        archive_bytes=b"not-a-zip",
    )

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:3] == ["git", "clone", "--depth"]:
            return subprocess.CompletedProcess(
                args, 128, "", "fatal: repository not found"
            )
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ProjectSkillInstallError):
        list_remote_project_skills("owner/repo")

    assert created_roots
    assert all(not root.exists() for root in created_roots)


def test_temp_materialization_is_removed_after_clone_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_roots = _track_temporary_directories(monkeypatch)
    _install_fake_github(
        monkeypatch,
        archive_bytes=None,
        http_errors={"https://api.github.com/repos/owner/repo": 404},
    )

    def fake_run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(args, 1, "", "no auth")
        if args[:3] == ["git", "clone", "--depth"]:
            return subprocess.CompletedProcess(
                args, 128, "", "fatal: repository not found"
            )
        raise AssertionError(f"Unexpected subprocess args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ProjectSkillInstallError):
        install_project_skill("owner/repo", workspace=Path.cwd())

    assert created_roots
    assert all(not root.exists() for root in created_roots)


def test_install_project_skill_rejects_missing_name_or_description(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/SKILL.md": "---\nname: \n---\n\n# Broken\n",
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    with pytest.raises(
        ProjectSkillInstallError,
        match="No valid skills found. Skills require a SKILL.md with name and description.",
    ):
        install_project_skill("owner/repo", workspace=tmp_path)
    assert "missing non-empty 'name'" in capsys.readouterr().err


def test_install_project_skill_rejects_unsupported_manifest_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/SKILL.md": "---\nname\n---\n\n# Broken\n",
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    with pytest.raises(
        ProjectSkillInstallError,
        match="No valid skills found. Skills require a SKILL.md with name and description.",
    ):
        install_project_skill("owner/repo", workspace=tmp_path)
    assert "not a key-value pair" in capsys.readouterr().err


def test_install_project_skill_accepts_folded_description_block_scalar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/skills/compress/SKILL.md": (
                "---\n"
                "name: compress\n"
                "description: >\n"
                "  Compress natural language memory files into a shorter form.\n"
                "  Preserve code blocks, links, and commands.\n"
                "---\n\n"
                "# Compress\n"
            ),
            "repo-main/skills/compress/scripts/__init__.py": "",
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    result = install_project_skill(
        "owner/repo",
        workspace=tmp_path,
        skill_name="compress",
    )

    assert result.name == "compress"
    installed = tmp_path / ".agents" / "skills" / "compress" / "SKILL.md"
    assert installed.is_file()
    assert "description: >" in installed.read_text(encoding="utf-8")


def test_install_project_skill_rejects_block_scalar_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/skills/compress/SKILL.md": (
                "---\n"
                "name: >\n"
                "  compress\n"
                "  helper\n"
                "description: Compress memory files.\n"
                "---\n\n"
                "# Compress\n"
            ),
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    with pytest.raises(
        ProjectSkillInstallError,
        match="No valid skills found. Skills require a SKILL.md with name and description.",
    ):
        install_project_skill("owner/repo", workspace=tmp_path)

    assert "unsupported block scalar for key 'name'" in capsys.readouterr().err


def test_install_project_skill_ignores_nested_metadata_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/skills/vitepress/SKILL.md": (
                "---\n"
                "name: vitepress\n"
                "description: VitePress static site generator skill.\n"
                "metadata:\n"
                "  author: Anthony Fu\n"
                '  version: "2026.1.28"\n'
                "---\n\n"
                "# VitePress\n"
            ),
            "repo-main/skills/vitepress/references/core-config.md": "# Config\n",
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    result = install_project_skill(
        "owner/repo",
        workspace=tmp_path,
        skill_name="vitepress",
    )

    assert result.name == "vitepress"
    installed = tmp_path / ".agents" / "skills" / "vitepress" / "SKILL.md"
    assert installed.is_file()


def test_install_project_skill_ignores_indentless_sequence_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = _make_zip_archive(
        {
            "repo-main/skills/compress/SKILL.md": (
                "---\n"
                "name: compress\n"
                "description: Compress markdown-heavy notes.\n"
                "tools:\n"
                "- read_file\n"
                "- apply_patch\n"
                "---\n\n"
                "# Compress\n"
            )
        }
    )
    _install_fake_github(monkeypatch, archive_bytes=archive_bytes)

    result = install_project_skill(
        "owner/repo",
        workspace=tmp_path,
        skill_name="compress",
    )

    assert result.name == "compress"
    installed = tmp_path / ".agents" / "skills" / "compress" / "SKILL.md"
    assert installed.is_file()
