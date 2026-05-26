"""Git status and diff helpers for the web workspace file tree."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pbi_agent.web.git_ignore import filter_gitignored_paths

GitFileStatus = Literal["M", "A", "D", "R", "U", "?"]
GitDiffError = Literal[
    "not_git_repository",
    "not_found",
    "binary",
    "outside_workspace",
    "git_failed",
]

_STATUS_PRIORITY: dict[GitFileStatus, int] = {
    "U": 60,
    "R": 50,
    "D": 40,
    "M": 30,
    "A": 20,
    "?": 10,
}


@dataclass(frozen=True, slots=True)
class GitStatusSnapshot:
    is_repository: bool
    statuses: dict[str, GitFileStatus]
    version: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class GitDiffSnapshot:
    path: str
    diff: str | None = None
    error: GitDiffError | None = None


def workspace_git_status(root: Path) -> GitStatusSnapshot:
    """Return combined staged/unstaged display status for paths in ``root``."""

    try:
        completed = _run_git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
    except OSError as exc:
        return GitStatusSnapshot(
            is_repository=False,
            statuses={},
            version=None,
            error=str(exc),
        )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        if "not a git repository" in stderr.lower():
            return GitStatusSnapshot(is_repository=False, statuses={}, version=None)
        return GitStatusSnapshot(
            is_repository=False,
            statuses={},
            version=None,
            error=stderr or "git status failed",
        )

    statuses = _parse_porcelain_z(completed.stdout)
    ignored_filtered_paths = filter_gitignored_paths(root, statuses)
    filtered_statuses: dict[str, GitFileStatus] = {
        path: statuses[path] for path in ignored_filtered_paths
    }
    return GitStatusSnapshot(
        is_repository=True,
        statuses=filtered_statuses,
        version=_status_version(root, filtered_statuses),
    )


def workspace_git_diff(root: Path, path: str) -> GitDiffSnapshot:
    clean_path = path.strip().replace("\\", "/")
    try:
        _resolve_workspace_path(root, clean_path)
    except (OSError, ValueError):
        return GitDiffSnapshot(path=clean_path, error="outside_workspace")

    status = workspace_git_status(root)
    if not status.is_repository:
        return GitDiffSnapshot(path=clean_path, error="not_git_repository")
    file_status = status.statuses.get(clean_path)
    if file_status is None:
        return GitDiffSnapshot(path=clean_path, error="not_found")
    if file_status == "?":
        return _untracked_diff(root, clean_path)

    try:
        completed = _run_git(root, "diff", "HEAD", "--no-ext-diff", "--", clean_path)
    except OSError:
        return GitDiffSnapshot(path=clean_path, error="git_failed")
    if completed.returncode != 0:
        return GitDiffSnapshot(path=clean_path, error="git_failed")
    diff = completed.stdout.decode("utf-8", errors="replace")
    if "Binary files " in diff:
        return GitDiffSnapshot(path=clean_path, error="binary")
    return GitDiffSnapshot(path=clean_path, diff=diff)


def _parse_porcelain_z(raw: bytes) -> dict[str, GitFileStatus]:
    entries = raw.decode("utf-8", errors="surrogateescape").split("\0")
    statuses: dict[str, GitFileStatus] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            continue
        xy = entry[:2]
        path = entry[3:]
        status = _display_status(xy)
        if status == "R" and index < len(entries):
            index += 1
        _merge_status(statuses, path, status)
    return statuses


def _display_status(xy: str) -> GitFileStatus:
    if "U" in xy or xy in {"AA", "DD"}:
        return "U"
    if "R" in xy:
        return "R"
    if "D" in xy:
        return "D"
    if "M" in xy:
        return "M"
    if "A" in xy:
        return "A"
    if xy == "??":
        return "?"
    return "M"


def _merge_status(
    statuses: dict[str, GitFileStatus],
    path: str,
    status: GitFileStatus,
) -> None:
    current = statuses.get(path)
    if current is None or _STATUS_PRIORITY[status] > _STATUS_PRIORITY[current]:
        statuses[path] = status


def _status_version(root: Path, statuses: dict[str, GitFileStatus]) -> str:
    digest = hashlib.sha1()
    for path, status in sorted(statuses.items()):
        digest.update(status.encode())
        digest.update(b"\0")
        digest.update(path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        if status == "D":
            continue
        try:
            stat_result = _resolve_workspace_path(root, path).stat()
        except OSError:
            continue
        digest.update(str(stat_result.st_mtime_ns).encode())
        digest.update(b"\0")
        digest.update(str(stat_result.st_size).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _untracked_diff(root: Path, path: str) -> GitDiffSnapshot:
    target = _resolve_workspace_path(root, path)
    if not target.exists() or not target.is_file():
        return GitDiffSnapshot(path=path, error="not_found")
    raw = target.read_bytes()
    if b"\0" in raw:
        return GitDiffSnapshot(path=path, error="binary")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return GitDiffSnapshot(path=path, error="binary")
    lines = content.splitlines(keepends=True)
    diff_lines = [
        f"diff --git a/{path} b/{path}\n",
        "new file mode 100644\n",
        "index 0000000..0000000\n",
        "--- /dev/null\n",
        f"+++ b/{path}\n",
        f"@@ -0,0 +1,{len(lines)} @@\n",
    ]
    diff_lines.extend(f"+{line}" for line in lines)
    if content and not content.endswith("\n"):
        diff_lines.append("\n\\ No newline at end of file\n")
    return GitDiffSnapshot(path=path, diff="".join(diff_lines))


def _resolve_workspace_path(root: Path, path: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    return target


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
