from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pbi_agent.web.input_mentions as input_mentions
from pbi_agent.web.input_mentions import (
    WorkspaceFileIndex,
    expand_file_mentions,
    expand_input_mentions,
    search_input_mentions,
)
from pbi_agent.web.scan import WorkspaceScanResult


def test_expand_file_mentions_appends_workspace_file_content(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("hello report\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        "Summarize @report.md",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize report.md"


def test_expand_file_mentions_warns_for_missing_file(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        "Summarize @missing.md",
        root=tmp_path,
    )

    assert expanded == "Summarize @missing.md"
    assert warnings == ["Referenced file not found: missing.md"]


def test_expand_file_mentions_ignores_outside_workspace_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        expanded, warnings = expand_file_mentions(
            f"Check @{outside}",
            root=tmp_path,
        )
    finally:
        outside.unlink(missing_ok=True)

    assert expanded == f"Check @{outside}"
    assert warnings == []


def test_expand_file_mentions_ignores_import_aliases(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        'import { Button } from "@/components/ui/button"',
        root=tmp_path,
    )

    assert expanded == 'import { Button } from "@/components/ui/button"'
    assert warnings == []


def test_expand_file_mentions_skips_email_addresses(tmp_path: Path) -> None:
    expanded, warnings = expand_file_mentions(
        "contact me at user@example.com",
        root=tmp_path,
    )

    assert expanded == "contact me at user@example.com"
    assert warnings == []


def test_expand_input_mentions_extracts_image_paths(tmp_path: Path) -> None:
    target = tmp_path / "mockup.png"
    target.write_bytes(b"not-used-by-parser")

    expanded, file_paths, image_paths, warnings = expand_input_mentions(
        "Review @mockup.png carefully",
        root=tmp_path,
    )

    assert expanded == "Review mockup.png carefully"
    assert file_paths == ["mockup.png"]
    assert image_paths == ["mockup.png"]
    assert warnings == []


def test_expand_file_mentions_supports_escaped_spaces(tmp_path: Path) -> None:
    target = tmp_path / "my notes.txt"
    target.write_text("hello notes\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        r"Summarize @my\ notes.txt",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize my notes.txt"


def test_expand_file_mentions_supports_literal_spaces(tmp_path: Path) -> None:
    target = tmp_path / "my notes.txt"
    target.write_text("hello notes\n", encoding="utf-8")

    expanded, warnings = expand_file_mentions(
        "Summarize @my notes.txt please",
        root=tmp_path,
    )

    assert warnings == []
    assert expanded == "Summarize my notes.txt please"


def test_expand_file_mentions_resolves_valid_path_before_long_prose(
    tmp_path: Path,
) -> None:
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    target = commands_dir / "ship-task.md"
    target.write_text("ship it\n", encoding="utf-8")

    expanded, file_paths, image_paths, warnings = expand_input_mentions(
        "Update @.agents/commands/ship-task.md "
        "we need to add instruction to wait for github workflow before merging PR",
        root=tmp_path,
    )

    assert expanded == (
        "Update .agents/commands/ship-task.md "
        "we need to add instruction to wait for github workflow before merging PR"
    )
    assert file_paths == [".agents/commands/ship-task.md"]
    assert image_paths == []
    assert warnings == []


def test_expand_file_mentions_warns_for_overlong_unresolved_path(
    tmp_path: Path,
) -> None:
    overlong_name = "a" * 300 + ".md"

    expanded, warnings = expand_file_mentions(
        f"Summarize @{overlong_name}",
        root=tmp_path,
    )

    assert expanded == f"Summarize @{overlong_name}"
    assert warnings == ["Referenced file path is too long and was ignored."]


def test_search_input_mentions_returns_ranked_matches(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "docs" / "maintainer.md").write_text("owner\n", encoding="utf-8")
    (tmp_path / "domain.txt").write_text("domain\n", encoding="utf-8")

    results = search_input_mentions("ma", root=tmp_path, limit=10)

    assert [item.path for item in results] == [
        "main.py",
        "docs/maintainer.md",
        "domain.txt",
    ]


def test_search_input_mentions_includes_hidden_nonignored_directories(
    tmp_path: Path,
) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "plan.md").write_text("---\nname: plan\n---\n", encoding="utf-8")
    (tmp_path / "planning.md").write_text("visible\n", encoding="utf-8")

    results = search_input_mentions("plan", root=tmp_path, limit=10)

    assert ".agents/commands/plan.md" in [item.path for item in results]


def test_search_input_mentions_skips_gitignored_directories(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "main.js").write_text("ignored\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")

    results = search_input_mentions("ma", root=tmp_path, limit=10)

    assert [item.path for item in results] == ["main.py"]


def test_workspace_file_index_returns_snapshot_while_refreshing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scans_started = threading.Event()
    release_second_scan = threading.Event()
    scan_count = 0

    def fake_scan(_root: Path):
        nonlocal scan_count
        scan_count += 1
        if scan_count == 1:
            return WorkspaceScanResult(files=["main.py"])
        scans_started.set()
        release_second_scan.wait(timeout=2)
        return WorkspaceScanResult(files=["other.py"])

    monkeypatch.setattr(input_mentions, "scan_workspace_files", fake_scan)
    index = WorkspaceFileIndex(tmp_path)
    index.warm_cache()
    index.wait_for_refresh(timeout=2)

    index.refresh_cache()
    assert scans_started.wait(timeout=2)
    payload = index.search("ma", limit=10)
    release_second_scan.set()
    index.wait_for_refresh(timeout=2)

    assert [item.path for item in payload.items] == ["main.py"]
    assert payload.scan_status == "scanning"
    assert payload.is_stale is True
    assert scan_count == 2
