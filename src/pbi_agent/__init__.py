"""pbi-agent package."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

__all__ = ["__version__"]


def _read_local_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.is_file():
        return "0.0.0"

    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get(
        "project", {}
    )
    project_version = project.get("version")
    return project_version if isinstance(project_version, str) else "0.0.0"


def _resolve_version() -> str:
    try:
        return version("pbi-agent")
    except PackageNotFoundError:
        return _read_local_version()


__version__ = _resolve_version()
