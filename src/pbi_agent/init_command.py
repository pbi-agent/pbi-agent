"""``pbi-agent init`` – scaffold a new Power BI report project.

Copies the bundled PBIP template into the current working directory so the
agent (or the user) has a ready-to-edit report structure.
"""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path


# Items inside the report package that should NOT be copied to the user's
# project (Python packaging artefacts, caches, etc.).
_SKIP = {"__init__.py", "__pycache__"}


def init_report(dest: Path, *, force: bool = False) -> Path:
    """Copy the bundled report template into *dest*.

    Parameters
    ----------
    dest:
        Target directory.  The template contents are placed directly inside
        this directory (i.e. ``dest/template_report.pbip``, etc.).
    force:
        If ``True``, overwrite existing files.  Otherwise raise if any of the
        template entries already exist in *dest*.

    Returns
    -------
    Path
        The *dest* directory (for convenience).

    Raises
    ------
    FileExistsError
        If *force* is ``False`` and a template file/directory already exists
        at the destination.
    """
    source_traversable = files("pbi_agent").joinpath("report")

    with as_file(source_traversable) as source_path:
        _copy_tree(source_path, dest, force=force)

    return dest


def _copy_tree(src: Path, dst: Path, *, force: bool) -> None:
    """Recursively copy *src* into *dst*, skipping packaging artefacts."""
    dst.mkdir(parents=True, exist_ok=True)

    for entry in sorted(src.iterdir()):
        if entry.name in _SKIP:
            continue

        target = dst / entry.name

        if entry.is_dir():
            if target.exists() and not force:
                raise FileExistsError(
                    f"Directory already exists: {target}\nUse --force to overwrite."
                )
            if target.exists() and force:
                shutil.rmtree(target)
            shutil.copytree(entry, target)
        else:
            if target.exists() and not force:
                raise FileExistsError(
                    f"File already exists: {target}\nUse --force to overwrite."
                )
            shutil.copy2(entry, target)
