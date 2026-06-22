from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pbi_agent.config import Settings
from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.matchers import hook_matches
from pbi_agent.hooks.output_parser import parse_hook_output
from pbi_agent.hooks.runtime import HookRuntime
from pbi_agent.hooks.schemas import HookEventName, HookTrustStatus
from pbi_agent.hooks.trust import HookTrustStore


def _write_hooks(path: Path, command: str, *, event: str = "PreToolUse") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    event: [
                        {
                            "matcher": "shell",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command,
                                    "timeout": 5,
                                    "statusMessage": "checking",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_discovery_marks_untrusted_then_trusted(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(hooks_path, "echo '{}'")
    trust = HookTrustStore(tmp_path / "state.json")

    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=trust,
    )

    assert len(discovery.hooks) == 1
    hook = discovery.hooks[0]
    assert hook.trust_status == HookTrustStatus.UNTRUSTED
    trust.trust(hook.key, hook.current_hash)

    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(tmp_path / "state.json"),
    )
    assert trusted.hooks[0].trust_status == HookTrustStatus.TRUSTED


def test_discovery_marks_modified_and_disabled(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(hooks_path, "echo '{}'")
    state_path = tmp_path / "state.json"
    trust = HookTrustStore(state_path)
    first = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=trust,
    ).hooks[0]
    trust.trust(first.key, first.current_hash)
    _write_hooks(hooks_path, "echo '{\"changed\":true}'")

    modified = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    ).hooks[0]
    assert modified.trust_status == HookTrustStatus.MODIFIED

    trust = HookTrustStore(state_path)
    trust.set_enabled(first.key, False)
    _write_hooks(hooks_path, "echo '{}'")
    disabled = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    ).hooks[0]
    assert disabled.trust_status == HookTrustStatus.DISABLED


def test_matchers() -> None:
    assert hook_matches(None, "shell")
    assert hook_matches("", "shell")
    assert hook_matches("*", "shell")
    assert hook_matches("shell|apply_patch", "apply_patch")
    assert not hook_matches("shell|apply_patch", "web_search")
    assert hook_matches("^mcp\\.", "mcp.tool")


def test_parse_pre_tool_rewrite_and_exit_code_block() -> None:
    parsed = parse_hook_output(
        event=HookEventName.PRE_TOOL_USE,
        stdout=json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "updatedInput": {"command": "echo rewritten"},
                }
            }
        ),
        stderr="",
        exit_code=0,
    )
    assert parsed.updated_input == {"command": "echo rewritten"}

    blocked = parse_hook_output(
        event=HookEventName.PRE_TOOL_USE,
        stdout="",
        stderr="nope",
        exit_code=2,
    )
    assert blocked.block_reason == "nope"
    assert not blocked.continue_

    empty_blocked = parse_hook_output(
        event=HookEventName.USER_PROMPT_SUBMIT,
        stdout="",
        stderr="",
        exit_code=2,
    )
    assert empty_blocked.block_reason == "Blocked by hook."
    assert not empty_blocked.continue_

    post_feedback = parse_hook_output(
        event=HookEventName.POST_TOOL_USE,
        stdout="",
        stderr="",
        exit_code=2,
    )
    assert post_feedback.replacement == "Hook provided feedback."

    stop_continuation = parse_hook_output(
        event=HookEventName.STOP,
        stdout="",
        stderr="",
        exit_code=2,
    )
    assert stop_continuation.continuation_prompt == "Continue after hook request."


def test_parse_pre_tool_codex_json_deny() -> None:
    parsed = parse_hook_output(
        event=HookEventName.PRE_TOOL_USE,
        stdout=json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Blocked by policy.",
                },
            }
        ),
        stderr="",
        exit_code=0,
    )

    assert not parsed.continue_
    assert parsed.block_reason == "Blocked by policy."


def test_parse_post_tool_codex_json_replacement_and_context() -> None:
    parsed = parse_hook_output(
        event=HookEventName.POST_TOOL_USE,
        stdout=json.dumps(
            {
                "systemMessage": "common context",
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "replacement": "model-visible replacement",
                    "additionalContext": "post context",
                },
            }
        ),
        stderr="",
        exit_code=0,
    )

    assert parsed.replacement == "model-visible replacement"
    assert parsed.additional_context == "post context"


def test_discovery_hook_keys_survive_unrelated_reordering(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    hooks_path = workspace / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "shell",
                            "hooks": [{"type": "command", "command": "echo shell"}],
                        },
                        {
                            "matcher": "apply_patch",
                            "hooks": [{"type": "command", "command": "echo patch"}],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    first = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(tmp_path / "state.json"),
    )
    shell_hook = next(hook for hook in first.hooks if hook.matcher == "shell")
    patch_hook = next(hook for hook in first.hooks if hook.matcher == "apply_patch")

    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "apply_patch",
                            "hooks": [{"type": "command", "command": "echo patch"}],
                        },
                        {
                            "matcher": "shell",
                            "hooks": [{"type": "command", "command": "echo shell"}],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    reordered = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(tmp_path / "state.json"),
    )

    assert next(hook for hook in reordered.hooks if hook.matcher == "shell").key == (
        shell_hook.key
    )
    assert (
        next(hook for hook in reordered.hooks if hook.matcher == "apply_patch").key
        == patch_hook.key
    )


def test_discovery_hook_keys_survive_same_matcher_reordering(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    hooks_path = workspace / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    def write_commands(commands: list[str]) -> None:
        hooks_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "shell",
                                "hooks": [
                                    {"type": "command", "command": command}
                                    for command in commands
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

    write_commands(["echo first", "echo second"])
    first = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(tmp_path / "state.json"),
    )
    keys_by_command = {hook.handler.command: hook.key for hook in first.hooks}

    write_commands(["echo inserted", "echo second", "echo first"])
    reordered = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(tmp_path / "state.json"),
    )

    assert {
        hook.handler.command: hook.key
        for hook in reordered.hooks
        if hook.handler.command in keys_by_command
    } == keys_by_command


def test_runtime_sends_stdin_and_skips_untrusted(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    script = workspace / "hook.py"
    script.write_text(
        "import json, sys\n"
        "data=json.load(sys.stdin)\n"
        "print(json.dumps({'systemMessage': data['tool_name']}))\n",
        encoding="utf-8",
    )
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(hooks_path, f"{sys.executable} hook.py")
    state_path = tmp_path / "state.json"
    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    runtime = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=discovery,
    )
    skipped = runtime.run(
        HookEventName.PRE_TOOL_USE,
        matcher_value="shell",
        payload={"tool_name": "shell"},
    )
    assert skipped.context_text is None

    hook = discovery.hooks[0]
    trust = HookTrustStore(state_path)
    trust.trust(hook.key, hook.current_hash)
    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    runtime = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=trusted,
    )
    result = runtime.run(
        HookEventName.PRE_TOOL_USE,
        matcher_value="shell",
        payload={"tool_name": "shell"},
    )
    assert result.context_text == "shell"


def test_runtime_user_prompt_submit_and_stop_ignore_matchers(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    script = workspace / "hook.py"
    script.write_text(
        "import json, sys\n"
        "data=json.load(sys.stdin)\n"
        "print(json.dumps({'systemMessage': data['hook_event_name']}))\n",
        encoding="utf-8",
    )
    hooks_path = workspace / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "matcher": "^never$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{sys.executable} hook.py",
                                }
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "matcher": "^never$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{sys.executable} hook.py",
                                }
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    trust = HookTrustStore(state_path)
    for hook in discovery.hooks:
        trust.trust(hook.key, hook.current_hash)
    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    runtime = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=trusted,
    )

    for event in (HookEventName.USER_PROMPT_SUBMIT, HookEventName.STOP):
        result = runtime.run(event)

        assert result.context_text == event.value
        assert len(result.runs) == 1


def test_runtime_ignores_failed_hook_output(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    script = workspace / "hook.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({\n"
        "    'hookSpecificOutput': {\n"
        "        'hookEventName': 'PreToolUse',\n"
        "        'permissionDecision': 'deny',\n"
        "        'permissionDecisionReason': 'should not apply',\n"
        "        'updatedInput': {'command': 'echo rewritten'},\n"
        "    }\n"
        "}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(hooks_path, f"{sys.executable} hook.py")
    state_path = tmp_path / "state.json"
    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    hook = discovery.hooks[0]
    trust = HookTrustStore(state_path)
    trust.trust(hook.key, hook.current_hash)
    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )

    result = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=trusted,
    ).run(
        HookEventName.PRE_TOOL_USE,
        matcher_value="shell",
        payload={"tool_name": "shell"},
    )

    assert result.runs[0].status.value == "failed"
    assert not result.blocked
    assert result.block_reason is None
    assert result.updated_input is None


def test_runtime_timeout(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(
        hooks_path,
        f'{sys.executable} -c "import time; time.sleep(2)"',
    )
    raw = json.loads(hooks_path.read_text(encoding="utf-8"))
    raw["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 1
    hooks_path.write_text(json.dumps(raw), encoding="utf-8")
    state_path = tmp_path / "state.json"
    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    hook = discovery.hooks[0]
    trust = HookTrustStore(state_path)
    trust.trust(hook.key, hook.current_hash)
    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )

    result = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=trusted,
    ).run(HookEventName.PRE_TOOL_USE, matcher_value="shell")

    assert result.runs[0].status.value == "timed_out"


def test_runtime_timeout_kills_child_process_tree(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    child = workspace / "child_marker.py"
    child.write_text(
        "import pathlib, time\n"
        "time.sleep(2)\n"
        "pathlib.Path('survived.txt').write_text('alive', encoding='utf-8')\n",
        encoding="utf-8",
    )
    parent = workspace / "parent_hook.py"
    parent.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, 'child_marker.py'])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    hooks_path = workspace / ".agents" / "hooks.json"
    _write_hooks(hooks_path, f"{sys.executable} parent_hook.py")
    raw = json.loads(hooks_path.read_text(encoding="utf-8"))
    raw["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 1
    hooks_path.write_text(json.dumps(raw), encoding="utf-8")
    state_path = tmp_path / "state.json"
    discovery = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )
    hook = discovery.hooks[0]
    trust = HookTrustStore(state_path)
    trust.trust(hook.key, hook.current_hash)
    trusted = discover_hooks(
        workspace,
        Settings(),
        global_config_path=tmp_path / "missing.json",
        trust_store=HookTrustStore(state_path),
    )

    result = HookRuntime(
        workspace=workspace,
        settings=Settings(),
        discovery=trusted,
    ).run(HookEventName.PRE_TOOL_USE, matcher_value="shell")
    time.sleep(2.5)

    assert result.runs[0].status.value == "timed_out"
    assert not (workspace / "survived.txt").exists()
