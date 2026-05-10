from __future__ import annotations

import subprocess
from pathlib import Path

from pbi_agent.web.scan import scan_workspace_files


def _git_init(path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_scan_workspace_files_includes_nested_files_and_hidden_nonignored_files(
    tmp_path: Path,
) -> None:
    _git_init(tmp_path)
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "deep" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / ".agents" / "commands").mkdir(parents=True)
    (tmp_path / ".agents" / "commands" / "plan.md").write_text(
        "---\nname: plan\n---\n", encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text("TOKEN=\n", encoding="utf-8")

    result = scan_workspace_files(tmp_path)

    assert result.error is None
    assert result.files == [
        ".agents/commands/plan.md",
        ".env.example",
        "src/deep/app.py",
    ]


def test_scan_workspace_files_excludes_gitignored_files_and_folders(
    tmp_path: Path,
) -> None:
    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored.txt\nbuild/\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "bundle.js").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("kept\n", encoding="utf-8")

    result = scan_workspace_files(tmp_path)

    assert result.error is None
    assert ".gitignore" in result.files
    assert "kept.txt" in result.files
    assert "ignored.txt" not in result.files
    assert "build/bundle.js" not in result.files


def test_scan_workspace_files_fallback_walks_nested_non_git_workspace(
    tmp_path: Path,
) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "nested.txt").write_text("nested\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("internal\n", encoding="utf-8")

    result = scan_workspace_files(tmp_path)

    assert result.error is None
    assert result.files == ["a/b/nested.txt"]


def test_scan_workspace_files_child_git_workspace_ignores_parent_gitignore(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    _git_init(parent)
    (parent / ".gitignore").write_text("child/\n", encoding="utf-8")
    _git_init(child)
    (child / "visible.txt").write_text("visible\n", encoding="utf-8")

    result = scan_workspace_files(child)

    assert result.error is None
    assert result.files == ["visible.txt"]


def test_scan_workspace_files_rejects_outside_symlinks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    outside = tmp_path.parent / "outside-scan-target.txt"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        (tmp_path / "outside-link.txt").symlink_to(outside)
        (tmp_path / "inside.txt").write_text("inside\n", encoding="utf-8")

        result = scan_workspace_files(tmp_path)
    finally:
        outside.unlink(missing_ok=True)

    assert result.error is None
    assert "inside.txt" in result.files
    assert "outside-link.txt" not in result.files
