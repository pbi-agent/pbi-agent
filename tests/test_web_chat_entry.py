from __future__ import annotations

import pytest

from unittest.mock import patch

from pbi_agent.web import chat_entry


def test_run_starts_watchdog_and_launches_chat() -> None:
    with (
        patch("pbi_agent.web.chat_entry._start_parent_watchdog") as mock_watchdog,
        patch("pbi_agent.web.chat_entry.main", return_value=7) as mock_main,
    ):
        rc = chat_entry.run(["--parent-pid", "4321", "--verbose"])

    assert rc == 7
    mock_watchdog.assert_called_once_with(4321)
    mock_main.assert_called_once_with(["--verbose", "chat"])


def test_watch_parent_process_uses_pid_existence_check_on_posix() -> None:
    with (
        patch.object(chat_entry.os, "name", "posix"),
        patch(
            "pbi_agent.web.chat_entry.os.getppid",
            side_effect=AssertionError("getppid should not be used on posix"),
        ),
        patch(
            "pbi_agent.web.chat_entry.os.kill",
            side_effect=ProcessLookupError,
        ) as mock_kill,
        patch(
            "pbi_agent.web.chat_entry.os._exit",
            side_effect=SystemExit(0),
        ) as mock_exit,
    ):
        with pytest.raises(SystemExit):
            chat_entry._watch_parent_process(4321)

    mock_kill.assert_called_once_with(4321, 0)
    mock_exit.assert_called_once_with(0)
