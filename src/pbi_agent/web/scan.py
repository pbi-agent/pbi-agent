"""Gitignore-aware workspace file scanning for web file mentions."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from pbi_agent.web.git_ignore import filter_gitignored_paths

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
    normalized_paths = _normalize_paths(root, paths)
    return WorkspaceScanResult(files=filter_gitignored_paths(root, normalized_paths))


def _scan_with_stdlib(root: Path) -> WorkspaceScanResult:
    paths: list[str] = []
    try:
        _scan_directory_with_gitignore(root, root, [], paths)
    except OSError as exc:
        return WorkspaceScanResult(
            files=sorted(paths, key=str.casefold), error=str(exc)
        )
    return WorkspaceScanResult(files=sorted(paths, key=str.casefold))


@dataclass(frozen=True, slots=True)
class _GitignoreRule:
    base_path: str
    pattern: str
    negated: bool
    directory_only: bool
    basename_only: bool
    anchored: bool

    def matches(self, path: str, *, is_dir: bool) -> bool:
        if self.directory_only and not is_dir:
            return False
        relative_path = _relative_to_base(path, self.base_path)
        if relative_path is None:
            return False
        if self.basename_only and not self.anchored:
            return any(
                fnmatchcase(part, self.pattern)
                for part in relative_path.split("/")
                if part
            )
        return _match_path_from_base(relative_path, self.pattern)


def _scan_directory_with_gitignore(
    root: Path,
    directory: Path,
    inherited_rules: list[_GitignoreRule],
    paths: list[str],
) -> None:
    directory_relative_path = _relative_path(root, directory)
    rules = inherited_rules + _load_gitignore_rules(directory, directory_relative_path)
    for child in sorted(directory.iterdir(), key=lambda path: path.name.casefold()):
        child_relative_path = _relative_path(root, child)
        if child.name in _VCS_INTERNAL_DIRS:
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if _is_gitignored(child_relative_path, is_dir=is_dir, rules=rules):
            continue
        if child.is_symlink():
            if _is_outside_workspace_symlink(root, child) or is_dir:
                continue
        if is_dir:
            _scan_directory_with_gitignore(root, child, rules, paths)
        else:
            try:
                if child.is_file():
                    paths.append(child_relative_path)
            except OSError:
                continue


def _load_gitignore_rules(directory: Path, base_path: str) -> list[_GitignoreRule]:
    gitignore = directory / ".gitignore"
    if not gitignore.is_file():
        return []
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rules: list[_GitignoreRule] = []
    for line in lines:
        rule = _parse_gitignore_rule(line, base_path)
        if rule is not None:
            rules.append(rule)
    return rules


def _parse_gitignore_rule(line: str, base_path: str) -> _GitignoreRule | None:
    pattern = line.rstrip()
    if not pattern or pattern.startswith("#"):
        return None
    negated = pattern.startswith("!")
    if negated:
        pattern = pattern[1:]
    elif pattern.startswith(("\\#", "\\!")):
        pattern = pattern[1:]
    anchored = pattern.startswith("/")
    directory_only = pattern.endswith("/")
    pattern = pattern.strip("/")
    if not pattern:
        return None
    return _GitignoreRule(
        base_path=base_path,
        pattern=pattern,
        negated=negated,
        directory_only=directory_only,
        basename_only="/" not in pattern,
        anchored=anchored,
    )


def _is_gitignored(
    path: str,
    *,
    is_dir: bool,
    rules: list[_GitignoreRule],
) -> bool:
    ignored = False
    for rule in rules:
        if rule.matches(path, is_dir=is_dir):
            ignored = not rule.negated
    return ignored


def _relative_path(root: Path, path: Path) -> str:
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def _relative_to_base(path: str, base_path: str) -> str | None:
    if not base_path:
        return path
    prefix = f"{base_path}/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return None


def _match_path_from_base(path: str, pattern: str) -> bool:
    if pattern.startswith("**/") and _match_path_from_base(path, pattern[3:]):
        return True
    if "/" not in pattern and "/" in path:
        return False
    return PurePosixPath(f"/{path}").match(f"/{pattern}")


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
