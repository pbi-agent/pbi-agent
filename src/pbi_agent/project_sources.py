from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from dataclasses import dataclass
from pathlib import Path

_GITHUB_API_ROOT = "https://api.github.com"
_GITHUB_WEB_ROOT = "https://github.com"
_GITHUB_FALLBACK_STATUS_CODES = frozenset({401, 403, 404})
_GIT_TIMEOUT_SECONDS = 60
_PRIVATE_REPO_ERROR = (
    "Could not access GitHub repository {owner_repo}. Confirm repository access "
    "and git/SSH credentials are configured."
)


class ProjectSourceError(ValueError):
    """Raised when project source parsing or materialization fails."""


@dataclass(slots=True, frozen=True)
class GitHubProjectSource:
    source: str
    owner: str
    repo: str
    owner_repo: str
    tree_parts: tuple[str, ...] | None = None


@dataclass(slots=True, frozen=True)
class LocalProjectSource:
    source: str
    path: Path


@dataclass(slots=True, frozen=True)
class ResolvedGitHubSelection:
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class MaterializedProjectSource:
    repo_root: Path
    resolved_root: Path
    ref: str | None


class _GitHubHttpFailure(Exception):
    def __init__(self, *, url: str, status_code: int) -> None:
        super().__init__(f"{url} -> HTTP {status_code}")
        self.url = url
        self.status_code = status_code


class _GitHubArchiveFallbackNeeded(Exception):
    def __init__(self, source: GitHubProjectSource) -> None:
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


def parse_project_source(
    source: str,
    *,
    source_label: str,
) -> GitHubProjectSource | LocalProjectSource:
    normalized = source.strip()
    if not normalized:
        raise ProjectSourceError(
            f"{_label_cap(source_label)} source must not be empty."
        )

    if _looks_like_local_source(normalized):
        return LocalProjectSource(
            source=normalized,
            path=Path(normalized).expanduser(),
        )

    return parse_github_project_source(normalized, source_label=source_label)


def parse_github_project_source(
    source: str,
    *,
    source_label: str,
) -> GitHubProjectSource:
    normalized = source.strip()
    if not normalized:
        raise ProjectSourceError(
            f"{_label_cap(source_label)} source must not be empty."
        )

    shorthand_match = _fullmatch_owner_repo(normalized.rstrip("/"))
    if shorthand_match is not None:
        owner, repo = shorthand_match
        return GitHubProjectSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
        )

    try:
        parsed_url = urllib.parse.urlparse(normalized)
    except ValueError as exc:
        raise ProjectSourceError(
            f"Unsupported {source_label} source: {source}"
        ) from exc

    if parsed_url.scheme not in {"http", "https"} or parsed_url.netloc != "github.com":
        raise ProjectSourceError(
            f"Unsupported {source_label} source. Use a local path, owner/repo, "
            "a GitHub repository URL, or a GitHub tree URL."
        )

    parts = [urllib.parse.unquote(part) for part in parsed_url.path.split("/") if part]
    if len(parts) < 2:
        raise ProjectSourceError(
            "Unsupported GitHub URL. Expected https://github.com/<owner>/<repo>."
        )

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise ProjectSourceError(
            "Unsupported GitHub URL. Expected https://github.com/<owner>/<repo>."
        )

    if len(parts) == 2:
        return GitHubProjectSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
        )

    if len(parts) >= 4 and parts[2] == "tree":
        tree_parts = tuple(part for part in parts[3:] if part)
        if not tree_parts:
            raise ProjectSourceError(
                "Unsupported GitHub tree URL. Expected a ref after /tree/."
            )
        return GitHubProjectSource(
            source=normalized,
            owner=owner,
            repo=repo,
            owner_repo=f"{owner}/{repo}",
            tree_parts=tree_parts,
        )

    raise ProjectSourceError(
        "Unsupported GitHub URL. Use a repository URL or a tree URL."
    )


def sanitize_project_subpath(subpath: str, *, source_label: str) -> str:
    normalized = subpath.replace("\\", "/")
    for segment in normalized.split("/"):
        if segment == "..":
            raise ProjectSourceError(
                f'Unsafe {source_label} subpath: "{subpath}" contains path traversal segments.'
            )
    return normalized.strip("/")


def resolve_github_source_ref(
    source: GitHubProjectSource,
    *,
    source_label: str,
) -> str:
    token = _lookup_github_token()
    if source.tree_parts:
        selection = _resolve_github_tree_selection_from_api(
            source,
            token=token,
            source_label=source_label,
        )
        return _require_resolved_github_ref(selection, source=source)
    return _resolve_default_branch_via_api(
        source,
        token=token,
        source_label=source_label,
    )


def materialize_project_source(
    source: GitHubProjectSource | LocalProjectSource,
    *,
    temp_root: Path,
    source_label: str,
    user_agent: str,
    allow_local_file: bool = False,
) -> MaterializedProjectSource:
    if isinstance(source, LocalProjectSource):
        resolved_root = _resolve_local_source_root(
            source.path,
            source_label=source_label,
            allow_file=allow_local_file,
        )
        repo_root = resolved_root.parent if resolved_root.is_file() else resolved_root
        return MaterializedProjectSource(
            repo_root=repo_root.resolve(),
            resolved_root=resolved_root.resolve(),
            ref=None,
        )

    token = _lookup_github_token()
    try:
        return _materialize_github_archive(
            source,
            temp_root=temp_root,
            token=token,
            source_label=source_label,
            user_agent=user_agent,
        )
    except _GitHubArchiveFallbackNeeded:
        return _materialize_github_with_git(
            source,
            temp_root=temp_root,
            source_label=source_label,
        )


def _materialize_github_archive(
    source: GitHubProjectSource,
    *,
    temp_root: Path,
    token: str | None,
    source_label: str,
    user_agent: str,
) -> MaterializedProjectSource:
    selection = _resolve_github_selection_from_api(
        source,
        token=token,
        source_label=source_label,
    )
    selection_ref = _require_resolved_github_ref(selection, source=source)
    archive_url = (
        f"{_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}/zipball/"
        f"{urllib.parse.quote(selection_ref, safe='')}"
    )
    try:
        archive_bytes = _read_github_bytes(
            archive_url,
            token=token,
            user_agent=user_agent,
        )
    except _GitHubHttpFailure as exc:
        if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise ProjectSourceError(
            f"GitHub request failed for {exc.url}: HTTP {exc.status_code}."
        ) from exc

    try:
        repo_root = _extract_archive_bytes(
            archive_bytes,
            destination=temp_root / "archive",
        )
    except ProjectSourceError as exc:
        if "not a valid zip file" in str(exc):
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise

    resolved_root = _resolve_repo_selection_root(
        repo_root,
        selection.subpath,
        source_label=source_label,
    )
    return MaterializedProjectSource(
        repo_root=repo_root,
        resolved_root=resolved_root,
        ref=selection.ref,
    )


def _materialize_github_with_git(
    source: GitHubProjectSource,
    *,
    temp_root: Path,
    source_label: str,
) -> MaterializedProjectSource:
    clone_root = temp_root / "clone"
    clone_root.mkdir(parents=True, exist_ok=True)

    selection = _resolve_github_selection_from_git(source, source_label=source_label)
    repo_root = _clone_github_repo(
        source,
        destination=clone_root / "repo",
        ref=selection.ref,
    )
    resolved_root = _resolve_repo_selection_root(
        repo_root,
        selection.subpath,
        source_label=source_label,
    )
    return MaterializedProjectSource(
        repo_root=repo_root,
        resolved_root=resolved_root,
        ref=selection.ref,
    )


def _require_resolved_github_ref(
    selection: ResolvedGitHubSelection,
    *,
    source: GitHubProjectSource,
) -> str:
    if selection.ref is None:
        raise ProjectSourceError(
            f"Could not resolve a GitHub ref for {source.owner_repo}."
        )
    return selection.ref


def _resolve_github_selection_from_api(
    source: GitHubProjectSource,
    *,
    token: str | None,
    source_label: str,
) -> ResolvedGitHubSelection:
    if source.tree_parts:
        return _resolve_github_tree_selection_from_api(
            source,
            token=token,
            source_label=source_label,
        )
    return ResolvedGitHubSelection(
        ref=_resolve_default_branch_via_api(
            source,
            token=token,
            source_label=source_label,
        ),
        subpath=None,
    )


def _resolve_github_selection_from_git(
    source: GitHubProjectSource,
    *,
    source_label: str,
) -> ResolvedGitHubSelection:
    if source.tree_parts:
        return _resolve_github_tree_selection_from_git(
            source,
            source_label=source_label,
        )
    return ResolvedGitHubSelection(ref=None, subpath=None)


def _resolve_default_branch_via_api(
    source: GitHubProjectSource,
    *,
    token: str | None,
    source_label: str,
) -> str:
    repo_url = f"{_GITHUB_API_ROOT}/repos/{source.owner}/{source.repo}"
    try:
        payload = _read_github_json(
            repo_url,
            token=token,
            user_agent=f"pbi-agent-{source_label}s",
        )
    except _GitHubHttpFailure as exc:
        if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
            raise _GitHubArchiveFallbackNeeded(source) from exc
        raise ProjectSourceError(
            f"GitHub request failed for {exc.url}: HTTP {exc.status_code}."
        ) from exc

    default_branch = payload.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise ProjectSourceError(
            f"Could not resolve the default branch for {source.owner_repo}."
        )
    return default_branch


def _resolve_github_tree_selection_from_api(
    source: GitHubProjectSource,
    *,
    token: str | None,
    source_label: str,
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
            source_label=source_label,
        )
        if exists is True:
            subpath = "/".join(tree_parts[split_index:]) or None
            if subpath is not None:
                subpath = sanitize_project_subpath(
                    subpath,
                    source_label=source_label,
                )
            return ResolvedGitHubSelection(ref=ref_candidate, subpath=subpath)
        if exists is None:
            any_unavailable = True

    if any_unavailable:
        raise _GitHubArchiveFallbackNeeded(source)

    fallback_ref = tree_parts[0]
    subpath = "/".join(tree_parts[1:]) or None
    if subpath is not None:
        subpath = sanitize_project_subpath(subpath, source_label=source_label)
    return ResolvedGitHubSelection(ref=fallback_ref, subpath=subpath)


def _resolve_github_tree_selection_from_git(
    source: GitHubProjectSource,
    *,
    source_label: str,
) -> ResolvedGitHubSelection:
    tree_parts = list(source.tree_parts or ())
    refs = _git_ls_remote_refs(source)

    for split_index in range(len(tree_parts), 0, -1):
        ref_candidate = "/".join(tree_parts[:split_index])
        if ref_candidate not in refs:
            continue
        subpath = "/".join(tree_parts[split_index:]) or None
        if subpath is not None:
            subpath = sanitize_project_subpath(subpath, source_label=source_label)
        return ResolvedGitHubSelection(ref=ref_candidate, subpath=subpath)

    fallback_ref = tree_parts[0]
    subpath = "/".join(tree_parts[1:]) or None
    if subpath is not None:
        subpath = sanitize_project_subpath(subpath, source_label=source_label)
    return ResolvedGitHubSelection(ref=fallback_ref, subpath=subpath)


def _github_ref_exists_via_api(
    *,
    owner: str,
    repo: str,
    ref: str,
    token: str | None,
    source_label: str,
) -> bool | None:
    quoted_ref = urllib.parse.quote(ref, safe="")
    unavailable = False

    for namespace in ("heads", "tags"):
        url = (
            f"{_GITHUB_API_ROOT}/repos/{owner}/{repo}/git/matching-refs/"
            f"{namespace}/{quoted_ref}"
        )
        try:
            payload = _read_github_json_value(
                url,
                token=token,
                user_agent=f"pbi-agent-{source_label}s",
            )
        except _GitHubHttpFailure as exc:
            if exc.status_code in _GITHUB_FALLBACK_STATUS_CODES:
                unavailable = True
                continue
            raise ProjectSourceError(
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


def _resolve_local_source_root(
    path: Path,
    *,
    source_label: str,
    allow_file: bool,
) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        raise ProjectSourceError(f"Local {source_label} source {path} does not exist.")
    if resolved.is_dir():
        return resolved
    if allow_file and resolved.is_file():
        return resolved
    raise ProjectSourceError(
        f"Local {source_label} source {path} is not a "
        f"{'file or directory' if allow_file else 'directory'}."
    )


def _extract_archive_bytes(archive_bytes: bytes, *, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ProjectSourceError(
            "GitHub archive response was not a valid zip file."
        ) from exc

    with archive:
        top_level_dirs: set[str] = set()
        destination_root = destination.resolve()
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ProjectSourceError(
                    f"Archive contains unsafe member path: {member.filename!r}."
                )
            if not member.filename:
                continue

            unix_mode = member.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ProjectSourceError(
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
        raise ProjectSourceError(
            "GitHub archive did not contain a single repository root."
        )

    return (destination_root / next(iter(top_level_dirs))).resolve()


def _resolve_repo_selection_root(
    repo_root: Path,
    subpath: str | None,
    *,
    source_label: str,
) -> Path:
    if subpath is None:
        return repo_root.resolve()

    candidate = (repo_root / subpath).resolve()
    _ensure_path_within_root(repo_root.resolve(), candidate)
    if not candidate.exists():
        raise ProjectSourceError(
            f"Remote path {subpath!r} was not found in the materialized repository."
        )
    return candidate


def _read_github_json_value(
    url: str,
    *,
    token: str | None,
    user_agent: str,
) -> object:
    payload = _read_github_bytes(url, token=token, user_agent=user_agent)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectSourceError(f"Failed to parse JSON response from {url}.") from exc


def _read_github_json(
    url: str,
    *,
    token: str | None,
    user_agent: str,
) -> dict[str, object]:
    data = _read_github_json_value(url, token=token, user_agent=user_agent)
    if not isinstance(data, dict):
        raise ProjectSourceError(f"Unexpected JSON response from {url}.")
    return data


def _read_github_bytes(
    url: str,
    *,
    token: str | None,
    user_agent: str,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers=_github_request_headers(token, user_agent=user_agent),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise _GitHubHttpFailure(url=url, status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ProjectSourceError(
            f"GitHub request failed for {url}: {exc.reason}."
        ) from exc


def _github_request_headers(
    token: str | None,
    *,
    user_agent: str,
) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": user_agent,
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
    source: GitHubProjectSource,
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
            raise ProjectSourceError(
                f"Git clone failed for {source.owner_repo}: {_compact_git_error(exc.stderr)}"
            ) from exc
        try:
            _run_git_clone(ssh_url, destination=destination, ref=ref)
        except _GitCommandFailure as ssh_exc:
            if _git_error_is_auth_style(ssh_exc.stderr):
                raise ProjectSourceError(
                    _PRIVATE_REPO_ERROR.format(owner_repo=source.owner_repo)
                ) from ssh_exc
            raise ProjectSourceError(
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


def _git_ls_remote_refs(source: GitHubProjectSource) -> set[str]:
    try:
        output = _git_ls_remote(source, https=True, extra_args=("--heads", "--tags"))
    except ProjectSourceError as exc:
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
    source: GitHubProjectSource,
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
            raise ProjectSourceError(
                _PRIVATE_REPO_ERROR.format(owner_repo=source.owner_repo)
            ) from exc
        raise ProjectSourceError(
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
        raise ProjectSourceError(
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


def _looks_like_local_source(value: str) -> bool:
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
        raise ProjectSourceError(f"Path {candidate} escapes the allowed root {root}.")


def _fullmatch_owner_repo(value: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"([^/]+)/([^/]+?)(?:\.git)?", value)
    if match is None:
        return None
    owner = match.group(1)
    repo = match.group(2)
    if not owner or not repo:
        return None
    return owner, repo


def _label_cap(value: str) -> str:
    return value[:1].upper() + value[1:]
