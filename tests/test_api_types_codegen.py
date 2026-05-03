from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "generate_api_types.py"
SPEC = importlib.util.spec_from_file_location("generate_api_types", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load API type generator.")
generate_api_types = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_api_types)


def test_generated_api_types_are_current() -> None:
    assert (
        generate_api_types.OUTPUT.read_text(encoding="utf-8")
        == generate_api_types.render_api_types()
    )


def test_generated_api_types_include_sse_event_union() -> None:
    generated = generate_api_types.render_api_types()

    assert "export type SseEventModel =" in generated
    assert "InputStateSseEventModel" in generated
    assert "LiveSessionEndedSseEventModel" in generated
