from __future__ import annotations

from .entrypoint import main
from .parser import (
    CleanHelpFormatter,
    ExplicitPortAction,
    _argv_with_default_command,
    _default_command_insertion_index,
    _subcommand_names,
    _web_runtime_flags_in_args,
    build_parser,
)
from .shared import DEFAULT_COMMAND, DEFAULT_SANDBOX_IMAGE
from .web import WebServerWaitResult

_MODULE_ATTRS = (
    "parser",
    "entrypoint",
    "web",
    "run",
    "sandbox",
    "config",
    "catalogs",
    "kanban",
    "sessions",
    "shared",
)


def __getattr__(name: str):
    for module_name in _MODULE_ATTRS:
        module = __import__(f"{__name__}.{module_name}", fromlist=[name])
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CleanHelpFormatter",
    "DEFAULT_COMMAND",
    "DEFAULT_SANDBOX_IMAGE",
    "ExplicitPortAction",
    "WebServerWaitResult",
    "_argv_with_default_command",
    "_default_command_insertion_index",
    "_subcommand_names",
    "_web_runtime_flags_in_args",
    "build_parser",
    "main",
]
