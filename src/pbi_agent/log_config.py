import logging
from pathlib import Path


def configure_logging(verbose: bool) -> None:
    console_level = logging.DEBUG if verbose else logging.WARNING

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [console_handler]

    log_path: Path | None = None
    if verbose:
        log_path = Path.cwd() / "pbi-agent-debug.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        handlers=handlers,
        force=True,
    )

    if log_path is not None:
        logging.getLogger(__name__).debug("Debug log file: %s", log_path)
