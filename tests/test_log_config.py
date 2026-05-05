import logging
from pathlib import Path

from pbi_agent.log_config import configure_logging


def test_configure_logging_is_quiet_by_default() -> None:
    configure_logging(verbose=False)

    root_logger = logging.getLogger()

    assert root_logger.level == logging.WARNING
    assert len(root_logger.handlers) == 1
    assert root_logger.handlers[0].level == logging.WARNING


def test_configure_logging_verbose_enables_debug(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    configure_logging(verbose=True)

    root_logger = logging.getLogger()

    assert root_logger.level == logging.DEBUG
    assert len(root_logger.handlers) == 2
    assert root_logger.handlers[0].level == logging.DEBUG
    assert (tmp_path / "pbi-agent-debug.log").exists()
