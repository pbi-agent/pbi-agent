from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.table import Table

from pbi_agent.skills.project_catalog import (
    SkillManifestError,
    load_project_skill_manifest,
)

DEFAULT_SKILLS_SOURCE = "pbi-agent/skills"
_GITHUB_API_ROOT = "https://api.github.com"
_GITHUB_WEB_ROOT = "https://github.com"
_GITHUB_FALLBACK_STATUS_CODES = frozenset({401, 403, 404})
_GIT_TIMEOUT_SECONDS = 60
_INSTALL_ROOT = Path(".agents/skills")
_PRIVATE_REPO_ERROR = (
    "Could not access GitHub repository {owner_repo}. Confirm repository access "
    "and git/SSH credentials are configured."
)


class ProjectSkillInstallError(ValueError):
    """Raised when project skill installation fails."""


@dataclass(slots=True, frozen=True)
class GitHubSkillSource:
    source: str
    owner: str
    repo: str
    owner_repo: str
    tree_parts: tuple[str, ...] | None = None


@dataclass(slots=True, frozen=True)
class LocalSkillSource:
    source: str
    path: Path


@dataclass(slots=True, frozen=True)
class ResolvedGitHubSelection:
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class RemoteSkillCandidateSummary:
    name: str
    description: str
    subpath: str | None


@dataclass(slots=True, frozen=True)
class RemoteSkillListing:
    source: str
    ref: str | None
    candidates: list[RemoteSkillCandidateSummary]


@dataclass(slots=True, frozen=True)
class ProjectSkillInstallResult:
    name: str
    install_path: Path
    source: str
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class _RemoteSkillCandidate:
    name: str
    description: str
    skill_dir: Path
    repo_subpath: str | None


@dataclass(slots=True, frozen=True)
class _MaterializedSkillSource:
    repo_root: Path
    resolved_root: Path
    ref: str | None


class _GitHubHttpFailure(Exception):
    def __init__(self, *, url: str, status_code: int) -> None:
        super().__init__(f"{url} -> HTTP {status_code}")
        self.url = url
        self.status_code = status_code


class _GitHubArchiveFallbackNeeded(Exception):
    def __init__(self, source: GitHubSkillSource) -> None:
        super().__init__(source.source)
        self.source = source


class _GitCommandFailure(Exception):
    def __init__(
        self,
        *,
        args: tuple[str, ...],
        returncode: int,
        stderr: str,
    ) -> None:
        super().__init__(stderr)
        self.args = args
        self.returncode = returncode
        self.stderr = stderr


def resolve_default_skills_source() -> str:
    return DEFAULT_SKILLS_SOURCE


def render_remote_skill_listing(
    listing: RemoteSkillListing,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    table = Table(title="Available Skills", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Source Path", style="dim")
    for candidate in listing.candidates:
        table.add_row(candidate.name, candidate.description, candidate.subpath or ".")
    active_console.print(table)
    return 0


def list_remote_project_skills(source: str) -> RemoteSkillListing:
    parsed_source = parse_project_skill_source(source)
    with TemporaryDirectory(prefix="pbi-agent-skill-") as temp_dir:
        materialized = _materialize_skill_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_skill_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
        )

    if not candidates:
        raise ProjectSkillInstallError(
            "No valid skills found. Skills require a SKILL.md with name and description."
        )

    return RemoteSkillListing(
        source=source,
        ref=materialized.ref,
        candidates=[
            RemoteSkillCandidateSummary(
                name=candidate.name,
                description=candidate.description,
                subpath=candidate.repo_subpath,
            )
            for candidate in candidates
        ],
    )


def install_project_skill(
    source: str,
    *,
    skill_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectSkillInstallResult:
    parsed_source = parse_project_skill_source(source)
    install_workspace = (workspace or Path.cwd()).resolve()
    install_root = (install_workspace / _INSTALL_ROOT).resolve()

    with TemporaryDirectory(prefix="pbi-agent-skill-") as temp_dir:
        materialized = _materialize_skill_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_skill_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
        )
        selected = _select_remote_skill_candidate(candidates, skill_name=skill_name)
        target_dir = _resolve_install_target(
            install_root=install_root,
            skill_name=selected.name,
        )
        _prepare_install_target(target_dir, force=force)
        shutil.copytree(selected.skill_dir, target_dir)

    return ProjectSkillInstallResult(
        name=selected.name,
        install_path=target_dir,
        source=source,
        ref=materialized.ref,
        subpath=selected.repo_subpath,
    )


def parse_project_skill_source(source: str) -> GitHubSkillSource | LocalSkillSource:
    normalized = source.strip()
    if not normalized:
        raise ProjectSkillInstallError("Skill source must not be empty.")

    if _looks_like_local_skill_source(normalized):
        return LocalSkillSource(
            source=normalized,
            path=Path(normalized).expanduser(),
        )

    return parse_github_skill_source(normalized)


def parse_github_skill_source(source: str) -> GitHubSkillSource:
    normalized = source.strip()
    if not normalized:
        raise ProjectSkillInstallError("Skill source must not be empty.")

    shorthand_match = re_fullmatch_owner_repo(normalized.rstrip("/"))
    if shorthand_match is not None:
        owner, repo = shorthand_match
        return GitHubSkillSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
        )

    try:
        parsed_url = urllib.parse.urlparse(normalized)
    except ValueError as exc:
        raise ProjectSkillInstallError(f"Unsupported skill source: {source}") from exc

    if parsed_url.scheme not in {"http", "https"} or parsed_url.netloc != "github.com":
        raise ProjectSkillInstallError(
            "Unsupported skill source. Use a local path, owner/repo, a GitHub "
            "repository URL, or a GitHub tree URL."
        )

    parts = [urllib.parse.unquote(part) for part in parsed_url.path.split("/") if part]
    if len(parts) < 2:
        raise ProjectSkillInstallError(
            "Unsupported GitHub URL. Expected https://github.com/<owner>/<repo>."
        )

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise ProjectSkillInstallError(
            "Unsupported GitHub URL. Expected https://github.com/<owner>/<repo>."
        )

    if len(parts) == 2:
        return GitHubSkillSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
        )

    if len(parts) >= 4 and parts[2] == "tree":
        tree_parts = tuple(part for part in parts[3:] if part)
        if not tree_parts:
            raise ProjectSkillInstallError(
                "Unsupported GitHub tree URL. Expected a ref after /tree/."
            )
        return GitHubSkillSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
            tree_parts=tree_parts,
        )

    raise ProjectSkillInstallError(
        "Unsupported GitHub URL. Use a repository URL or a tree URL."
    )


def sanitize_skill_subpath(subpath: str) -> str:
    normalized = subpath.replace("\\", "/")
    for segment in normalized.split("/"):
        if segment == "..":
            raise ProjectSkillInstallError(
                f'Unsafe subpath: "{subpath}" contains path traversal segments.'
            )
    return normalized.strip("/")


def resolve_github_source_ref(source: GitHubSkillSource) -> str:
    token = _lookup_github_token()
    if source.tree_parts:
        return _resolve_github_tree_selection_from_api(source, token=token).ref
    return _resolve_default_branch_via_api(source, token=token)


def _materialize_skill_source(
    source: GitHubSkillSource | LocalSkillSource,
    *,
    temp_root: Path,
) -> _MaterializedSkillSource:
    if isinstance(source, LocalSkillSource):
        resolved_root = _resolve_local_source_root(source.path)
        return _MaterializedSkillSource(
            repo_root=resolved_root,
            resolved_root=resolved_root,
            ref=None,
        )

    token = _lookup_github_token()
    try:
        return _materialize_github_archive(source, temp_root=temp_root, token=token)
    except _GitHubArchiveFallbackNeeded:
        return _materialize_github_with_git(source, temp_root=temp_root)


def _materialize_github_archive(
    source: GitHubSkillSource,
    *,
    temp_root: Path,
    token: str | None,
) -> _MaterializedSkillSource:
    selection = _resolve_github_selection_from_api(source, token=token)
    archive_url = (
        f"{_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}/zipball/"
        f"{urllib.parse.quote(selection.ref, safe='')}"
    )
    try:
        archive_bytes = _read_github_bytes(archive_url, token=token)
    except _GitHubHttpFailure as exc:
        if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise ProjectSkillInstallError(
            f"GitHub request failed for {exc.url}: HTTP {exc.status_code}."
        ) from exc

    try:
        repo_root = _extract_archive_bytes(
            archive_bytes,
            destination=temp_root / "archive",
        )
    except ProjectSkillInstallError as exc:
        if "not a valid zip file" in str(exc):
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise

    resolved_root = _resolve_repo_selection_root(repo_root, selection.subpath)
    return _MaterializedSkillSource(
        repo_root=repo_root,
        resolved_root=resolved_root,
        ref=selection.ref,
    )


def _materialize_github_with_git(
    source: GitHubSkillSource,
    *,
    temp_root: Path,
) -> _MaterializedSkillSource:
    clone_root = temp_root / "clone"
    clone_root.mkdir(parents=True, exist_ok=True)

    selection = _resolve_github_selection_from_git(source)
    repo_root = _clone_github_repo(
        source,
        destination=clone_root / "repo",
        ref=selection.ref,
    )
    resolved_root = _resolve_repo_selection_root(repo_root, selection.subpath)
    return _MaterializedSkillSource(
        repo_root=repo_root,
        resolved_root=resolved_root,
        ref=selection.ref,
    )


def _resolve_github_selection_from_api(
    source: GitHubSkillSource,
    *,
    token: str | None,
) -> ResolvedGitHubSelection:
    if source.tree_parts:
        return _resolve_github_tree_selection_from_api(source, token=token)
    return ResolvedGitHubSelection(
        ref=_resolve_default_branch_via_api(source, token=token),
        subpath=None,
    )


def _resolve_github_selection_from_git(
    source: GitHubSkillSource,
) -> ResolvedGitHubSelection:
    if source.tree_parts:
        return _resolve_github_tree_selection_from_git(source)
    return ResolvedGitHubSelection(ref=None, subpath=None)


def _resolve_default_branch_via_api(
    source: GitHubSkillSource,
    *,
    token: str | None,
) -> str:
    repo_url = f"{_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}"
    try:
        payload = _read_github_json(repo_url, token=token)
    except _GitHubHttpFailure as exc:
        if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise ProjectSkillInstallError(
            f"GitHub request failed for {exc.url}: HTTP {exc.status_code}."
        ) from exc

    default_branch = payload.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise ProjectSkillInstallError(
            f"Could not resolve the default branch for {source.owner_repo}."
        )
    return default_branch


def _resolve_github_tree_selection_from_api(
    source: GitHubSkillSource,
    *,
    token: str | None,
) -> ResolvedGitHubSelection:
    tree_parts = list(source.tree_parts or ())
    any_unavailable = False

    for split_index in range(len(tree_parts), 0, -1):
        ref_candidate = "/".join(tree_parts[:split_index])
        exists = _github_ref_exists_via_api(
            owner=source.owner,
            repo=source.repo,
            ref=ref_candidate,
            token=token,
        )
        if exists is True:
            subpath = "/".join(tree_parts[split_index:]) or None
            if subpath is not None:
                subpath = sanitize_skill_subpath(subpath)
            return ResolvedGitHubSelection(ref=ref_candidate, subpath=subpath)
        if exists is None:
            any_unavailable = True

    if any_unavailable:
        raise _GitHubArchiveFallbackNeeded(source)

    fallback_ref = tree_parts[0]
    subpath = "/".join(tree_parts[1:]) or None
    if subpath is not None:
        subpath = sanitize_skill_subpath(subpath)
    return ResolvedGitHubSelection(ref=fallback_ref, subpath=subpath)


def _resolve_github_tree_selection_from_git(
    source: GitHubSkillSource,
) -> ResolvedGitHubSelection:
    tree_parts = list(source.tree_parts or ())
    refs = _git_ls_remote_refs(source)

    for split_index in range(len(tree_parts), 0, -1):
        ref_candidate = "/".join(tree_parts[:split_index])
        if ref_candidate not in refs:
            continue
        subpath = "/".join(tree_parts[split_index:]) or None
        if subpath is not None:
            subpath = sanitize_skill_subpath(subpath)
        return ResolvedGitHubSelection(ref=ref_candidate, subpath=subpath)

    fallback_ref = tree_parts[0]
    subpath = "/".join(tree_parts[1:]) or None
    if subpath is not None:
        subpath = sanitize_skill_subpath(subpath)
    return ResolvedGitHubSelection(ref=fallback_ref, subpath=subpath)


def _github_ref_exists_via_api(
    *,
    owner: str,
    repo: str,
    ref: str,
    token: str | None,
) -> bool | None:
    quoted_ref = urllib.parse.quote(ref, safe="")
    unavailable = False

    for namespace in ("heads", "tags"):
        url = (
            f"{_GITHUB_API_ROOT}/repos/{owner}/{repo}/git/matching-refs/"
            f"{namespace}/{quoted_ref}"
        )
        try:
            payload = _read_github_json_value(url, token=token)
        except _GitHubHttpFailure as exc:
            if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
                unavailable = True
                continue
            raise ProjectSkillInstallError(
                f"GitHub request failed for {exc.url}: HTTP {exc.status_code}."
            ) from exc
        if not isinstance(payload, list):
            continue
        expected_ref = f"refs/{namespace}/{ref}"
        if any(
            isinstance(entry, dict) and entry.get("ref") == expected_ref
            for entry in payload
        ):
            return True

    if unavailable:
        return None
    return False


def _resolve_local_source_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        raise ProjectSkillInstallError(f"Local skill source {path} does not exist.")
    if not resolved.is_dir():
        raise ProjectSkillInstallError(f"Local skill source {path} is not a directory.")
    return resolved


def _extract_archive_bytes(archive_bytes: bytes, *, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ProjectSkillInstallError(
            "GitHub archive response was not a valid zip file."
        ) from exc

    with archive:
        top_level_dirs: set[str] = set()
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ProjectSkillInstallError(
                    f"Archive contains unsafe member path: {member.filename!r}."
                )
            if not member.filename:
                continue

            unix_mode = member.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ProjectSkillInstallError(
                    "Archive contains unsupported symbolic link member: "
                    f"{member.filename!r}."
                )

            top_level_dirs.add(member_path.parts[0])
            target_path = (destination_root / member_path).resolve()
            _ensure_path_within_root(destination_root, target_path)

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with (
                archive.open(member, "r") as source_file,
                target_path.open("wb") as target_file,
            ):
                shutil.copyfileobj(source_file, target_file)

    if len(top_level_dirs) != 1:
        raise ProjectSkillInstallError(
            "GitHub archive did not contain a single repository root."
        )

    return (destination_root / next(iter(top_level_dirs))).resolve()


def _resolve_repo_selection_root(repo_root: Path, subpath: str | None) -> Path:
    if subpath is None:
        return repo_root.resolve()

    candidate = (repo_root / subpath).resolve()
    _ensure_path_within_root(repo_root.resolve(), candidate)
    if not candidate.exists():
        raise ProjectSkillInstallError(
            f"Remote path {subpath!r} was not found in the materialized repository."
        )
    if not candidate.is_dir():
        raise ProjectSkillInstallError(f"Remote path {subpath!r} is not a directory.")
    return candidate


def _discover_remote_skill_candidates(
    *,
    repo_root: Path,
    resolved_root: Path,
) -> list[_RemoteSkillCandidate]:
    candidate_dirs: list[Path] = []
    seen_dirs: set[Path] = set()

    def enqueue(skill_dir: Path) -> None:
        resolved_dir = skill_dir.resolve()
        if resolved_dir in seen_dirs:
            return
        seen_dirs.add(resolved_dir)
        candidate_dirs.append(resolved_dir)

    if (resolved_root / "SKILL.md").is_file():
        enqueue(resolved_root)

    for container in (resolved_root / "skills",):
        if not container.is_dir():
            continue
        for child in sorted(container.iterdir(), key=lambda item: item.name.casefold()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                enqueue(child)

    candidates: list[_RemoteSkillCandidate] = []
    for skill_dir in candidate_dirs:
        try:
            manifest = load_project_skill_manifest(skill_dir / "SKILL.md")
        except SkillManifestError as exc:
            _warn(
                f"Skipping skill at {skill_dir / 'SKILL.md'}: unsupported manifest: {exc}"
            )
            continue

        repo_subpath = skill_dir.relative_to(repo_root).as_posix()
        candidates.append(
            _RemoteSkillCandidate(
                name=manifest.name,
                description=manifest.description,
                skill_dir=skill_dir,
                repo_subpath=None if repo_subpath == "." else repo_subpath,
            )
        )

    return candidates


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _select_remote_skill_candidate(
    candidates: list[_RemoteSkillCandidate],
    *,
    skill_name: str | None,
) -> _RemoteSkillCandidate:
    if not candidates:
        raise ProjectSkillInstallError(
            "No valid skills found. Skills require a SKILL.md with name and description."
        )

    if skill_name is None:
        if len(candidates) != 1:
            raise ProjectSkillInstallError(
                "Multiple skills were found in the source. Re-run with --list or "
                "--skill <name>."
            )
        return candidates[0]

    matched = [
        candidate
        for candidate in candidates
        if candidate.name.casefold() == skill_name.casefold()
    ]
    if not matched:
        available = ", ".join(candidate.name for candidate in candidates)
        raise ProjectSkillInstallError(
            f"Unknown skill {skill_name!r}. Available skills: {available}."
        )
    if len(matched) > 1:
        raise ProjectSkillInstallError(
            f"Skill name {skill_name!r} matched multiple remote skill bundles."
        )
    return matched[0]


def _resolve_install_target(*, install_root: Path, skill_name: str) -> Path:
    normalized_name = skill_name.strip()
    if not normalized_name:
        raise ProjectSkillInstallError("Skill manifest name must not be empty.")
    if (
        "/" in normalized_name
        or "\\" in normalized_name
        or normalized_name in {".", ".."}
    ):
        raise ProjectSkillInstallError(
            "Unsupported skill name "
            f"{skill_name!r}. Skill install names must be a single path segment."
        )

    install_root.mkdir(parents=True, exist_ok=True)
    target_dir = (install_root / normalized_name).resolve()
    _ensure_path_within_root(install_root.resolve(), target_dir)
    return target_dir


def _prepare_install_target(target_dir: Path, *, force: bool) -> None:
    if not target_dir.exists():
        return

    if not force:
        raise ProjectSkillInstallError(
            f"Skill already installed at {target_dir}. Re-run with --force to replace it."
        )

    if target_dir.is_symlink() or target_dir.is_file():
        target_dir.unlink()
        return
    shutil.rmtree(target_dir)


def _read_github_json_value(url: str, *, token: str | None) -> object:
    payload = _read_github_bytes(url, token=token)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectSkillInstallError(
            f"Failed to parse JSON response from {url}."
        ) from exc


def _read_github_json(url: str, *, token: str | None) -> dict[str, object]:
    data = _read_github_json_value(url, token=token)
    if not isinstance(data, dict):
        raise ProjectSkillInstallError(f"Unexpected JSON response from {url}.")
    return data


def _read_github_bytes(url: str, *, token: str | None) -> bytes:
    request = urllib.request.Request(
        url,
        headers=_github_request_headers(token),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise _GitHubHttpFailure(url=url, status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ProjectSkillInstallError(
            f"GitHub request failed for {url}: {exc.reason}."
        ) from exc


def _github_request_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pbi-agent-skills",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _lookup_github_token() -> str | None:
    for env_name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(env_name)
        if value and value.strip():
            return value.strip()

    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    token = completed.stdout.strip()
    return token or None


def _clone_github_repo(
    source: GitHubSkillSource,
    *,
    destination: Path,
    ref: str | None,
) -> Path:
    https_url = f"{_GITHUB_WEB_ROOT}/{source.owner_repo}.git"
    ssh_url = f"git@github.com:{source.owner_repo}.git"

    try:
        _run_git_clone(https_url, destination=destination, ref=ref)
    except _GitCommandFailure as exc:
        if not _git_error_is_auth_style(exc.stderr):
            raise ProjectSkillInstallError(
                f"Git clone failed for {source.owner_repo}: {_compact_git_error(exc.stderr)}"
            ) from exc
        try:
            _run_git_clone(ssh_url, destination=destination, ref=ref)
        except _GitCommandFailure as ssh_exc:
            if _git_error_is_auth_style(ssh_exc.stderr):
                raise ProjectSkillInstallError(
                    _PRIVATE_REPO_ERROR.format(owner_repo=source.owner_repo)
                ) from ssh_exc
            raise ProjectSkillInstallError(
                f"Git clone failed for {source.owner_repo}: "
                f"{_compact_git_error(ssh_exc.stderr)}"
            ) from ssh_exc

    return destination.resolve()


def _run_git_clone(remote_url: str, *, destination: Path, ref: str | None) -> None:
    args = ["git", "clone", "--depth", "1"]
    if ref:
        args.extend(["--branch", ref])
    args.extend([remote_url, str(destination)])
    _run_git_command(args)


def _git_ls_remote_refs(source: GitHubSkillSource) -> set[str]:
    try:
        output = _git_ls_remote(source, https=True, extra_args=("--heads", "--tags"))
    except ProjectSkillInstallError as exc:
        if _PRIVATE_REPO_ERROR.format(owner_repo=source.owner_repo) not in str(exc):
            raise
        output = _git_ls_remote(source, https=False, extra_args=("--heads", "--tags"))
    refs: set[str] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        ref_name = parts[1]
        if ref_name.startswith("refs/heads/"):
            refs.add(ref_name.removeprefix("refs/heads/"))
        elif ref_name.startswith("refs/tags/"):
            refs.add(ref_name.removeprefix("refs/tags/"))
    return refs


def _git_ls_remote(
    source: GitHubSkillSource,
    *,
    https: bool,
    extra_args: tuple[str, ...],
) -> str:
    remote_url = (
        f"{_GITHUB_WEB_ROOT}/{source.owner_repo}.git"
        if https
        else f"git@github.com:{source.owner_repo}.git"
    )
    args = ["git", "ls-remote", *extra_args, remote_url]
    try:
        return _run_git_command(args)
    except _GitCommandFailure as exc:
        if _git_error_is_auth_style(exc.stderr):
            raise ProjectSkillInstallError(
                _PRIVATE_REPO_ERROR.format(owner_repo=source.owner_repo)
            ) from exc
        raise ProjectSkillInstallError(
            f"Git ls-remote failed for {source.owner_repo}: {_compact_git_error(exc.stderr)}"
        ) from exc


def _run_git_command(args: list[str]) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except OSError as exc:
        raise ProjectSkillInstallError(
            f"Failed to run git command: {' '.join(args)} ({exc})"
        ) from exc

    if completed.returncode != 0:
        raise _GitCommandFailure(
            args=tuple(args),
            returncode=completed.returncode,
            stderr=completed.stderr.strip() or completed.stdout.strip(),
        )

    return completed.stdout


def _git_error_is_auth_style(message: str) -> bool:
    normalized = message.casefold()
    patterns = (
        "authentication failed",
        "repository not found",
        "permission denied",
        "could not read username",
        "could not read password",
        "could not read from remote repository",
        "support for password authentication was removed",
        "publickey",
    )
    return any(pattern in normalized for pattern in patterns)


def _compact_git_error(message: str) -> str:
    normalized = " ".join(line.strip() for line in message.splitlines() if line.strip())
    return normalized or "unknown git error"


def _looks_like_local_skill_source(value: str) -> bool:
    if value in {".", ".."}:
        return True
    if value.startswith(("./", "../", ".\\", "..\\", "~/", "~\\")):
        return True
    if value.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    return False


def _ensure_path_within_root(root: Path, candidate: Path) -> None:
    if candidate != root and root not in candidate.parents:
        raise ProjectSkillInstallError(
            f"Path {candidate} escapes the allowed root {root}."
        )


def re_fullmatch_owner_repo(value: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"([^/]+)/([^/]+?)(?:\.git)?", value)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2)
    if not owner or not repo:
        return None
    return owner, repo
