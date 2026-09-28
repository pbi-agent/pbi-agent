/simplify fixes for `pbi-agent upgrade`:

- [x] Move PyPI fetch, version compare, `UpdateCheckError` into `self_update.py`; `PYPI_URL` from `PACKAGE_NAME`; upgrade CLI stops importing maintenance (altitude 3, reuse minor).
- [x] `upgrade` skips the maintenance update check entirely (`check_updates=False`): no double PyPI fetch/detection (efficiency 1, altitude 2/4).
- [x] Notice built with its line break + shared `update_available_message()`; drop `replace(". ", ...)` surgery (altitude 1).
- [x] Drop `upgrade_hint` blanket fallback; use `detect_upgrade_plan().hint` (altitude 5).
- [x] CLI errors via `_print_error` (reuse 2).
- [x] self_update simplifications: `_installer_plan` single return, `_is_managed_env`, pip hint, field docstrings, `source_install_url` early returns (simplify 1-5).
- [x] cli/upgrade: pass narrowed `command`, drop asserts (simplify 6).
- [x] Tests: `SOURCE_PLAN`, parametrize near-duplicates, `make_http_response` fixture, timeout constant (simplify 7-8, reuse 3).
- [x] Validate: ruff, format, basedpyright, full pytest, docs build.
- [x] MEMORY.md task entry.
