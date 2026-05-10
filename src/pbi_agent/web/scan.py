"""Gitignore-aware workspace file scanning for web file mentions."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_VCS_INTERNAL_DIRS = frozenset({".git", ".hg", ".svn"})


@dataclass(frozen=True, slots=True)
class WorkspaceScanResult:
    """Result of a workspace file scan."""

    files: list[str] = field(default_factory=list)
    error: str | None = None


def scan_workspace_files(root: Path) -> WorkspaceScanResult:
    """Return safe POSIX file paths under ``root``, honoring Git ignores when possible."""

    workspace_root = root.resolve()
    git_result = _scan_git_workspace(workspace_root)
    if git_result is not None:
        return git_result
    return _scan_with_stdlib(workspace_root)


def _scan_git_workspace(root: Path) -> WorkspaceScanResult | None:
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-co",
                "--exclude-standard",
                "-z",
                "--",
                ".",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return WorkspaceScanResult(error=str(exc))

    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        return WorkspaceScanResult(error=message or "git ls-files failed")

    paths = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return WorkspaceScanResult(files=_normalize_paths(root, paths))


def _scan_with_stdlib(root: Path) -> WorkspaceScanResult:
    paths: list[str] = []
    try:
        for path in root.rglob("*"):
            if any(part in _VCS_INTERNAL_DIRS for part in path.relative_to(root).parts):
                continue
            if path.is_file() and not _is_outside_workspace_symlink(root, path):
                paths.append(path.relative_to(root).as_posix())
    except OSError as exc:
        return WorkspaceScanResult(
            files=sorted(paths, key=str.casefold), error=str(exc)
        )
    return WorkspaceScanResult(files=sorted(paths, key=str.casefold))


def _normalize_paths(root: Path, raw_paths: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        if not raw_path:
            continue
        path_text = raw_path.replace("\\", "/")
        candidate = Path(path_text)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        absolute = root / candidate
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError:
            continue
        if not relative or relative.startswith("../"):
            continue
        try:
            if not absolute.is_file():
                continue
            if _is_outside_workspace_symlink(root, absolute):
                continue
        except OSError:
            continue
        if relative not in seen:
            seen.add(relative)
            normalized.append(relative)
    return sorted(normalized, key=str.casefold)


def _is_outside_workspace_symlink(root: Path, path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        return True
    return False


__all__ = ["WorkspaceScanResult", "scan_workspace_files"]
