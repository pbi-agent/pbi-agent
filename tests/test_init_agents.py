from __future__ import annotations

from pathlib import Path

import pytest

import pbi_agent.init_agents as init_agents

from pbi_agent.agents.project_installer import (
    ProjectAgentInstallError,
    ProjectAgentInstallResult,
)
from pbi_agent.commands.project_installer import (
    ProjectCommandInstallError,
    ProjectCommandInstallResult,
)


def _command_contents(command_name: str) -> str:
    title = " ".join(part.capitalize() for part in command_name.split("-"))
    return (
        f"---\nname: {title}\ndescription: {title} command.\n---\n\n"
        f"# {title}\n\nRun {command_name}.\n"
    )


def _agent_contents(agent_name: str) -> str:
    return (
        f"---\nname: {agent_name}\ndescription: Reviews code changes.\n---\n\n"
        "Review code changes.\n"
    )


def _install_fake_bootstrap_installers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    command_failures: dict[str, Exception] | None = None,
    agent_failures: dict[str, Exception] | None = None,
) -> tuple[
    list[tuple[str, str | None, bool, Path]], list[tuple[str, str | None, bool, Path]]
]:
    command_calls: list[tuple[str, str | None, bool, Path]] = []
    agent_calls: list[tuple[str, str | None, bool, Path]] = []
    command_failures = command_failures or {}
    agent_failures = agent_failures or {}

    def fake_install_command(
        source: str,
        *,
        command_name: str | None = None,
        force: bool = False,
        workspace: Path | None = None,
    ) -> ProjectCommandInstallResult:
        assert command_name is not None
        root = (workspace or Path.cwd()).resolve()
        command_calls.append((source, command_name, force, root))
        failure = command_failures.get(command_name)
        if failure is not None:
            raise failure
        install_path = root / ".agents" / "commands" / f"{command_name}.md"
        if install_path.exists() and not force:
            raise ProjectCommandInstallError(
                f"Command already installed at {install_path}."
            )
        install_path.parent.mkdir(parents=True, exist_ok=True)
        install_path.write_text(_command_contents(command_name), encoding="utf-8")
        return ProjectCommandInstallResult(
            command_id=command_name,
            slash_alias=f"/{command_name}",
            install_path=install_path,
            source=source,
            ref=None,
            subpath=f"commands/{command_name}.md",
        )

    def fake_install_agent(
        source: str,
        *,
        agent_name: str | None = None,
        force: bool = False,
        workspace: Path | None = None,
    ) -> ProjectAgentInstallResult:
        assert agent_name is not None
        root = (workspace or Path.cwd()).resolve()
        agent_calls.append((source, agent_name, force, root))
        failure = agent_failures.get(agent_name)
        if failure is not None:
            raise failure
        install_path = root / ".agents" / "agents" / f"{agent_name}.md"
        if install_path.exists() and not force:
            raise ProjectAgentInstallError(
                f"Agent '{agent_name}' is already installed at {install_path}."
            )
        install_path.parent.mkdir(parents=True, exist_ok=True)
        install_path.write_text(_agent_contents(agent_name), encoding="utf-8")
        return ProjectAgentInstallResult(
            agent_name=agent_name,
            install_path=install_path,
            source=source,
            ref=None,
            subpath=f"agents/{agent_name}.md",
        )

    monkeypatch.setattr(init_agents, "install_project_command", fake_install_command)
    monkeypatch.setattr(init_agents, "install_project_agent", fake_install_agent)
    return command_calls, agent_calls


def test_init_workspace_bootstrap_installs_default_commands_and_agents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls, agent_calls = _install_fake_bootstrap_installers(monkeypatch)

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path)
    rendered = init_agents.format_init_bootstrap_result(result)

    assert result.agents_file.created
    assert [item.status for item in result.commands] == ["installed"] * len(
        init_agents.DEFAULT_INIT_COMMANDS
    )
    assert [item.status for item in result.agents] == ["installed"]
    assert [call[1] for call in command_calls] == list(
        init_agents.DEFAULT_INIT_COMMANDS
    )
    assert all(call[0] == init_agents.DEFAULT_COMMANDS_SOURCE for call in command_calls)
    assert [call[1] for call in agent_calls] == list(init_agents.DEFAULT_INIT_AGENTS)
    assert all(call[0] == init_agents.DEFAULT_AGENTS_SOURCE for call in agent_calls)
    for command_name in init_agents.DEFAULT_INIT_COMMANDS:
        assert (tmp_path / ".agents" / "commands" / f"{command_name}.md").is_file()
    assert (tmp_path / ".agents" / "agents" / "code-reviewer.md").is_file()
    assert not (tmp_path / ".agents" / "agents" / "plan.md").exists()
    assert (
        "Summary: 1 created, 9 installed, 0 overwritten, 0 skipped, 0 failed."
        in rendered
    )
    assert "Installed command `/execute`" in rendered
    assert "Installed sub-agent `code-reviewer`" in rendered


def test_init_workspace_bootstrap_skips_existing_default_items_without_installers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls, agent_calls = _install_fake_bootstrap_installers(monkeypatch)
    (tmp_path / "AGENTS.md").write_text("existing", encoding="utf-8")
    for command_name in init_agents.DEFAULT_INIT_COMMANDS:
        command_path = tmp_path / ".agents" / "commands" / f"{command_name}.md"
        command_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text("existing", encoding="utf-8")
    agent_path = tmp_path / ".agents" / "agents" / "code-reviewer.md"
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text("existing", encoding="utf-8")

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path)
    rendered = init_agents.format_init_bootstrap_result(result)

    assert not result.agents_file.created
    assert [item.status for item in result.commands] == ["skipped"] * len(
        init_agents.DEFAULT_INIT_COMMANDS
    )
    assert [item.status for item in result.agents] == ["skipped"]
    assert command_calls == []
    assert agent_calls == []
    assert (
        "Summary: 0 created, 0 installed, 0 overwritten, 10 skipped, 0 failed."
        in rendered
    )
    assert "Skipped command `/plan`" in rendered
    assert "Skipped sub-agent `code-reviewer`" in rendered


def test_init_workspace_bootstrap_force_overwrites_existing_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command_calls, agent_calls = _install_fake_bootstrap_installers(monkeypatch)
    (tmp_path / "AGENTS.md").write_text("existing", encoding="utf-8")
    for command_name in init_agents.DEFAULT_INIT_COMMANDS:
        command_path = tmp_path / ".agents" / "commands" / f"{command_name}.md"
        command_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text("old command", encoding="utf-8")
    agent_path = tmp_path / ".agents" / "agents" / "code-reviewer.md"
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text("old agent", encoding="utf-8")

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path, force=True)
    rendered = init_agents.format_init_bootstrap_result(result)

    assert result.agents_file.overwritten
    assert [item.status for item in result.commands] == ["overwritten"] * len(
        init_agents.DEFAULT_INIT_COMMANDS
    )
    assert [item.status for item in result.agents] == ["overwritten"]
    assert all(call[2] for call in command_calls)
    assert all(call[2] for call in agent_calls)
    assert (
        "Summary: 0 created, 0 installed, 10 overwritten, 0 skipped, 0 failed."
        in rendered
    )
    assert "Overwrote command `/execute`" in rendered
    assert "Overwrote sub-agent `code-reviewer`" in rendered
    assert "old command" not in (
        tmp_path / ".agents" / "commands" / "execute.md"
    ).read_text(encoding="utf-8")
    assert "old agent" not in agent_path.read_text(encoding="utf-8")


def test_init_workspace_bootstrap_treats_installer_already_installed_as_skip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_bootstrap_installers(
        monkeypatch,
        command_failures={
            "execute": ProjectCommandInstallError(
                "Command already installed at /tmp/execute.md."
            )
        },
        agent_failures={
            "code-reviewer": ProjectAgentInstallError(
                "Agent 'code-reviewer' is already installed at /tmp/code-reviewer.md."
            )
        },
    )

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path)

    assert result.commands[0].name == "execute"
    assert result.commands[0].status == "skipped"
    assert result.agents[0].status == "skipped"


def test_init_workspace_bootstrap_reports_catalog_failures_without_aborting_agents_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_bootstrap_installers(
        monkeypatch,
        command_failures={"review": ProjectCommandInstallError("catalog unavailable")},
        agent_failures={
            "code-reviewer": ProjectAgentInstallError("agent catalog unavailable")
        },
    )

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path)
    rendered = init_agents.format_init_bootstrap_result(result)

    assert result.agents_file.created
    assert (tmp_path / "AGENTS.md").is_file()
    assert result.commands[-1].name == "review"
    assert result.commands[-1].status == "failed"
    assert result.agents[0].status == "failed"
    assert "Failed command `/review`: catalog unavailable" in rendered
    assert "Failed sub-agent `code-reviewer`: agent catalog unavailable" in rendered


def test_init_workspace_bootstrap_reports_filesystem_failures_without_aborting_agents_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_fake_bootstrap_installers(
        monkeypatch,
        command_failures={"execute": FileExistsError("commands path is a file")},
        agent_failures={"code-reviewer": OSError("cannot write agent")},
    )

    result = init_agents.init_workspace_bootstrap(workspace=tmp_path)
    rendered = init_agents.format_init_bootstrap_result(result)

    assert result.agents_file.created
    assert (tmp_path / "AGENTS.md").is_file()
    assert result.commands[0].name == "execute"
    assert result.commands[0].status == "failed"
    assert result.agents[0].status == "failed"
    assert "Failed command `/execute`: commands path is a file" in rendered
    assert "Failed sub-agent `code-reviewer`: cannot write agent" in rendered
