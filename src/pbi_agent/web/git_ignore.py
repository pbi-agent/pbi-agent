"""Helpers for excluding paths that match Git ignore rules."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path


def filter_gitignored_paths(root: Path, paths: Iterable[str]) -> list[str]:
    """Return ``paths`` with entries matching Git ignore rules removed.

    ``git ls-files`` intentionally reports tracked files even when they match a
    later ignore rule. For workspace search/tree indexing we want ignore rules to
    behave as an indexing exclusion list, so this helper asks Git to evaluate the
    candidate paths with ``--no-index``.
    """

    path_list = list(paths)
    if not path_list:
        return []
    ignored_paths = gitignored_path_set(root, path_list)
    if ignored_paths is None:
        return path_list
    return [path for path in path_list if path not in ignored_paths]


def gitignored_path_set(root: Path, paths: Iterable[str]) -> set[str] | None:
    """Return ignored paths according to Git, or ``None`` when Git cannot check."""

    path_list = list(paths)
    if not path_list:
        return set()

    stdin = "\0".join(path_list).encode("utf-8", errors="surrogateescape") + b"\0"
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "check-ignore",
                "--no-index",
                "-z",
                "--stdin",
            ],
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode not in {0, 1}:
        return None

    return {
        path
        for path in completed.stdout.decode("utf-8", errors="surrogateescape").split(
            "\0"
        )
        if path
    }


__all__ = ["filter_gitignored_paths", "gitignored_path_set"]
