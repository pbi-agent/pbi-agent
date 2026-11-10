from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_safe_path(root: Path, raw_path: Any, *, default: str = ".") -> Path:
    path_value = raw_path if isinstance(raw_path, str) and raw_path.strip() else default
    candidate = Path(path_value)
    return (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )


def relative_workspace_path(root: Path, path: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(resolved)
