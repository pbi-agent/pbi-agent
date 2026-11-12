from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbi_agent import cli
from pbi_agent.kits.installer import (
    KitInstallError,
    KitSelectionRequiredError,
    install_kit,
)

_SKILL = "---\nname: {name}\ndescription: {name} workflow.\n---\n\n# {name}\n"
_COMMAND = "---\nname: {name}\ndescription: {name} command.\n---\n\nDo {name}.\n"
_AGENT = "---\nname: {name}\ndescription: {name} agent.\n---\n\nYou are {name}.\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_kit(root: Path, *, content_dir: str = "") -> Path:
    content = root / content_dir if content_dir else root
    _write(content / "skills" / "dax" / "SKILL.md", _SKILL.format(name="dax"))
    _write(content / "skills" / "dax" / "refs" / "notes.md", "notes\n")
    _write(
        content / "commands" / "model-review.md", _COMMAND.format(name="model-review")
    )
    _write(content / "agents" / "modeler.md", _AGENT.format(name="modeler"))
    _write(
        content / "mcp.json",
        json.dumps({"servers": {"fabric": {"type": "http", "url": "https://x/mcp"}}}),
    )
    _write(root / "AGENTS.md", "# Power BI rules\n\n- Use DAX.\n")
    _write(root / "README.md", "# Kit readme\n")
    return root


def _actions(result) -> dict[tuple[str, str], str]:
    return {(item.kind, item.name): item.action for item in result.items}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.mark.parametrize("content_dir", ["", ".agents"])
def test_install_kit_copies_all_parts(
    tmp_path: Path, workspace: Path, content_dir: str
) -> None:
    kit = _make_kit(tmp_path / "powerbi-kit", content_dir=content_dir)

    result = install_kit(str(kit), workspace=workspace)

    assert result.name == "powerbi-kit"
    assert result.applied
    assert _actions(result) == {
        ("skill", "dax"): "install",
        ("command", "/model-review"): "install",
        ("agent", "modeler"): "install",
        ("mcp", "fabric"): "install",
        ("instructions", "AGENTS.md"): "install",
    }
    agents_dir = workspace / ".agents"
    assert (
        agents_dir / "skills" / "dax" / "refs" / "notes.md"
    ).read_text() == "notes\n"
    assert (agents_dir / "commands" / "model-review.md").is_file()
    assert (agents_dir / "agents" / "modeler.md").is_file()
    assert json.loads((agents_dir / "mcp.json").read_text()) == {
        "servers": {"fabric": {"type": "http", "url": "https://x/mcp"}}
    }
    assert (workspace / "AGENTS.md").read_text() == (
        "<!-- kit:powerbi-kit:start -->\n"
        "# Power BI rules\n\n- Use DAX.\n"
        "<!-- kit:powerbi-kit:end -->\n"
    )
    # Root markdown such as README.md is never treated as a command or agent.
    assert not (agents_dir / "commands" / "readme.md").exists()


def test_install_kit_keeps_existing_items_without_force(
    tmp_path: Path, workspace: Path
) -> None:
    kit = _make_kit(tmp_path / "kit")
    _write(workspace / ".agents" / "commands" / "model-review.md", "mine\n")
    _write(
        workspace / ".agents" / "mcp.json",
        json.dumps(
            {"servers": {"fabric": {"command": "mine"}, "other": {"command": "o"}}}
        ),
    )
    _write(workspace / "AGENTS.md", "# My rules\n")

    result = install_kit(str(kit), workspace=workspace)

    actions = _actions(result)
    assert actions[("command", "/model-review")] == "skip"
    assert actions[("mcp", "fabric")] == "skip"
    assert actions[("skill", "dax")] == "install"
    assert actions[("instructions", "AGENTS.md")] == "install"
    assert (
        workspace / ".agents" / "commands" / "model-review.md"
    ).read_text() == "mine\n"
    servers = json.loads((workspace / ".agents" / "mcp.json").read_text())["servers"]
    assert servers == {"fabric": {"command": "mine"}, "other": {"command": "o"}}
    assert (
        (workspace / "AGENTS.md")
        .read_text()
        .startswith("# My rules\n\n<!-- kit:kit:start -->\n")
    )

    # A second run adds nothing, including no duplicate instructions block.
    before = (workspace / "AGENTS.md").read_text()
    rerun = install_kit(str(kit), workspace=workspace)
    assert set(_actions(rerun).values()) == {"skip"}
    assert (workspace / "AGENTS.md").read_text() == before


def test_install_kit_force_replaces_existing_items(
    tmp_path: Path, workspace: Path
) -> None:
    kit = _make_kit(tmp_path / "kit")
    install_kit(str(kit), workspace=workspace)
    _write(workspace / ".agents" / "skills" / "dax" / "stale.md", "stale\n")
    agents_md = workspace / "AGENTS.md"
    agents_md.write_text("# Mine\n\n" + agents_md.read_text() + "\n## After\n")
    _write(kit / "AGENTS.md", "# Updated rules\n")
    _write(
        workspace / ".agents" / "mcp.json",
        json.dumps(
            {"servers": {"fabric": {"command": "old"}, "other": {"command": "o"}}}
        ),
    )

    result = install_kit(str(kit), force=True, workspace=workspace)

    assert set(_actions(result).values()) == {"replace"}
    assert not (workspace / ".agents" / "skills" / "dax" / "stale.md").exists()
    assert agents_md.read_text() == (
        "# Mine\n\n<!-- kit:kit:start -->\n# Updated rules\n<!-- kit:kit:end -->\n"
        "\n## After\n"
    )
    servers = json.loads((workspace / ".agents" / "mcp.json").read_text())["servers"]
    assert servers == {
        "fabric": {"type": "http", "url": "https://x/mcp"},
        "other": {"command": "o"},
    }


def test_install_kit_dry_run_writes_nothing(tmp_path: Path, workspace: Path) -> None:
    kit = _make_kit(tmp_path / "kit")

    result = install_kit(str(kit), dry_run=True, workspace=workspace)

    assert not result.applied
    assert len(result.items) == 5
    assert list(workspace.iterdir()) == []


def test_install_kit_rejects_empty_kit(tmp_path: Path, workspace: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    _write(empty / "README.md", "nothing here\n")

    with pytest.raises(KitInstallError, match="No kit content found"):
        install_kit(str(empty), workspace=workspace)


def test_install_kit_invalid_workspace_mcp_fails_before_writing(
    tmp_path: Path, workspace: Path
) -> None:
    kit = _make_kit(tmp_path / "kit")
    _write(workspace / ".agents" / "mcp.json", "{not json")

    with pytest.raises(KitInstallError, match="Invalid JSON in workspace MCP config"):
        install_kit(str(kit), workspace=workspace)

    assert not (workspace / ".agents" / "skills").exists()
    assert not (workspace / "AGENTS.md").exists()


def test_cli_kits_add_installs_and_previews(
    tmp_path: Path,
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    kit = _make_kit(tmp_path / "kit")
    monkeypatch.chdir(workspace)

    assert cli.main(["kits", "add", str(kit), "--list"]) == 0
    assert "(preview)" in capsys.readouterr().out
    assert not (workspace / ".agents").exists()

    assert cli.main(["kits", "add", str(kit)]) == 0
    assert "installed" in capsys.readouterr().out
    assert (workspace / ".agents" / "agents" / "modeler.md").is_file()

    assert cli.main(["kits", "add", str(tmp_path / "missing")]) == 2
    assert "Error:" in capsys.readouterr().err


def _make_catalog(root: Path, names: tuple[str, ...] = ("alpha", "beta")) -> Path:
    for name in names:
        kit = root / "kits" / name
        _write(kit / "commands" / f"{name}-cmd.md", _COMMAND.format(name=f"{name}-cmd"))
        _write(kit / "kit.json", json.dumps({"description": f"{name} kit."}))
    # Repository-level files of the catalog itself are not kit content.
    _write(root / "AGENTS.md", "# Catalog maintenance rules\n")
    _write(root / "kits" / "empty" / "README.md", "not a kit\n")
    return root


def test_catalog_requires_kit_selection_and_lists_kits(
    tmp_path: Path, workspace: Path
) -> None:
    catalog = _make_catalog(tmp_path / "catalog")

    with pytest.raises(KitSelectionRequiredError) as excinfo:
        install_kit(str(catalog), workspace=workspace)

    assert [
        (kit.name, kit.description, kit.subpath) for kit in excinfo.value.listing.kits
    ] == [
        ("alpha", "alpha kit.", "kits/alpha"),
        ("beta", "beta kit.", "kits/beta"),
    ]
    assert list(workspace.iterdir()) == []


def test_catalog_installs_selected_kit(tmp_path: Path, workspace: Path) -> None:
    catalog = _make_catalog(tmp_path / "catalog")

    result = install_kit(str(catalog), kit_name="Beta", workspace=workspace)

    assert result.name == "beta"
    assert _actions(result) == {("command", "/beta-cmd"): "install"}
    assert not (workspace / "AGENTS.md").exists()
    assert not (workspace / ".agents" / "commands" / "alpha-cmd.md").exists()


def test_catalog_with_one_kit_needs_no_selection(
    tmp_path: Path, workspace: Path
) -> None:
    catalog = _make_catalog(tmp_path / "catalog", names=("solo",))

    assert install_kit(str(catalog), workspace=workspace).name == "solo"


def test_kit_name_errors(tmp_path: Path, workspace: Path) -> None:
    catalog = _make_catalog(tmp_path / "catalog")
    kit = _make_kit(tmp_path / "kit")

    with pytest.raises(KitInstallError, match=r"Unknown kit 'nope'.*alpha, beta"):
        install_kit(str(catalog), kit_name="nope", workspace=workspace)
    with pytest.raises(KitInstallError, match="single kit, not a catalog"):
        install_kit(str(kit), kit_name="alpha", workspace=workspace)


def test_cli_kits_add_uses_default_catalog(
    tmp_path: Path,
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog = _make_catalog(tmp_path / "catalog")
    monkeypatch.setattr("pbi_agent.kits.installer.DEFAULT_KITS_SOURCE", str(catalog))
    monkeypatch.chdir(workspace)

    assert cli.main(["kits", "add"]) == 0
    listing = capsys.readouterr().out
    assert "Available Kits" in listing
    assert "alpha kit." in listing
    assert list(workspace.iterdir()) == []

    assert cli.main(["kits", "add", "--kit", "alpha", "--list"]) == 0
    assert "(preview)" in capsys.readouterr().out
    assert list(workspace.iterdir()) == []

    assert cli.main(["kits", "add", "--kit", "alpha"]) == 0
    capsys.readouterr()
    assert (workspace / ".agents" / "commands" / "alpha-cmd.md").is_file()

    assert cli.main(["kits", "add", str(catalog)]) == 2
    assert "--kit <name>" in capsys.readouterr().err
