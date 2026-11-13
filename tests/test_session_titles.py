from __future__ import annotations

import hashlib
import io
import os
import stat
import sys
import tarfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from pbi_agent import local_assets, session_titles
from pbi_agent.local_assets import Asset
from pbi_agent.session_store import SessionStore
from pbi_agent.web.session_manager import WebSessionManager

FAKE_COMPLETION = """#!{python}
import sys
args = sys.argv[1:]
prompt = open(args[args.index("-f") + 1], encoding="utf-8").read()
assert prompt.endswith("<|im_start|>assistant\\n\\n"), prompt
if "explode" in prompt:
    sys.exit(3)
print('"Generated title." [end of text]')
"""


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, status: int) -> None:
        super().__init__(data)
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _asset(data: bytes, name: str = "file.bin") -> Asset:
    return Asset(
        f"https://example.invalid/{name}", hashlib.sha256(data).hexdigest(), len(data)
    )


def _serve(data: bytes, requests: list[str | None], *, honor_range: bool = True):
    def urlopen(request, timeout):
        del timeout
        header = request.get_header("Range")
        requests.append(header)
        if header and honor_range:
            return FakeResponse(data[int(header[len("bytes=") : -1]) :], 206)
        return FakeResponse(data, 200)

    return urlopen


@pytest.fixture
def ready_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An enabled title model whose llama-completion is a small script."""
    if os.name == "nt":
        pytest.skip("fake llama-completion is a POSIX script")
    monkeypatch.setenv(session_titles.ENABLED_ENV, "1")
    session_titles.model_path().parent.mkdir(parents=True)
    session_titles.model_path().write_bytes(b"gguf")
    binary = session_titles.runtime_dir() / "llama-test" / "llama-completion"
    binary.parent.mkdir(parents=True)
    binary.write_text(FAKE_COMPLETION.format(python=sys.executable))
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_download_resumes_partial_file_and_verifies(tmp_path: Path) -> None:
    data = os.urandom(5000)
    destination = tmp_path / "file.bin"
    destination.with_name("file.bin.part").write_bytes(data[:1200])
    requests: list[str | None] = []

    with patch("urllib.request.urlopen", _serve(data, requests)):
        local_assets.download(_asset(data), destination, tmp_path / "lock")

    assert requests == ["bytes=1200-"]
    assert destination.read_bytes() == data
    assert not destination.with_name("file.bin.part").exists()


def test_download_restarts_when_server_ignores_range(tmp_path: Path) -> None:
    data = os.urandom(3000)
    destination = tmp_path / "file.bin"
    destination.with_name("file.bin.part").write_bytes(b"stale")

    with patch("urllib.request.urlopen", _serve(data, [], honor_range=False)):
        local_assets.download(_asset(data), destination, tmp_path / "lock")

    assert destination.read_bytes() == data


def test_download_rejects_checksum_mismatch(tmp_path: Path) -> None:
    data = b"tampered"
    asset = Asset("https://example.invalid/file.bin", "0" * 64, len(data))
    destination = tmp_path / "file.bin"

    with (
        patch("urllib.request.urlopen", _serve(data, [])),
        pytest.raises(ValueError, match="checksum mismatch"),
    ):
        local_assets.download(asset, destination, tmp_path / "lock")

    assert not destination.exists()
    assert not destination.with_name("file.bin.part").exists()


def test_ensure_assets_downloads_runtime_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(session_titles.ENABLED_ENV, "1")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
        info = tarfile.TarInfo("llama-test/llama-completion")
        info.size = 2
        info.mode = 0o755
        bundle.addfile(info, io.BytesIO(b"#!"))
    runtime, model = archive.getvalue(), b"gguf-weights"
    files = {"runtime.tar.gz": runtime, "model.gguf": model}

    def urlopen(request, timeout):
        del timeout
        return FakeResponse(files[request.full_url.rsplit("/", 1)[-1]], 200)

    monkeypatch.setattr(session_titles, "MODEL", _asset(model, "model.gguf"))
    monkeypatch.setattr(
        session_titles, "runtime_asset", lambda: _asset(runtime, "runtime.tar.gz")
    )
    assert not session_titles.is_ready()

    with patch("urllib.request.urlopen", urlopen):
        session_titles.ensure_assets()

    assert session_titles.is_ready()
    assert session_titles.model_path().read_bytes() == model
    assert sorted(p.name for p in session_titles.assets_root().iterdir()) == [
        f"llama.cpp-{session_titles.LLAMA_CPP_TAG}",
        "oot-oneliner-Q4_K_M.gguf",
    ]


def test_ensure_assets_does_nothing_when_disabled() -> None:
    with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
        session_titles.ensure_assets()

    assert not session_titles.assets_root().exists()


def test_ensure_assets_skips_while_another_process_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(session_titles.ENABLED_ENV, "1")
    session_titles.assets_root().mkdir(parents=True)
    (session_titles.assets_root() / "download.lock").touch()

    with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
        session_titles.ensure_assets()

    assert not session_titles.is_ready()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Fix Docker cache." [end of text]\n', "Fix Docker cache"),
        ("\nFirst line\nsecond line", "First line"),
        ("x" * 200, "x" * 80),
        (" [end of text]", ""),
    ],
)
def test_clean_title(raw: str, expected: str) -> None:
    assert session_titles.clean_title(raw) == expected


@pytest.mark.usefixtures("ready_assets")
def test_generate_title_runs_llama_completion() -> None:
    assert (
        session_titles.generate_title("please fix the login bug") == "Generated title"
    )
    assert [p.name for p in session_titles.assets_root().glob("*.txt")] == []


@pytest.mark.usefixtures("ready_assets")
def test_generate_title_returns_none_on_failure() -> None:
    assert session_titles.generate_title("explode") is None
    assert session_titles.generate_title("   ") is None


def test_generate_title_returns_none_when_not_ready() -> None:
    assert session_titles.generate_title("hello") is None


def _submit_first_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, *, rename: bool = False
) -> str:
    from pbi_agent.config import Settings

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(str(tmp_path), "openai", "gpt-5.4", "")
    release = threading.Event()
    real_generate = session_titles.generate_title

    def gated_generate(value: str) -> str | None:
        release.wait(timeout=5)
        return real_generate(value)

    def fake_run_session_loop(_settings, display, **kwargs):
        del _settings, kwargs
        display.user_prompt()
        return 0

    manager = WebSessionManager(
        Settings(api_key="test-key", provider="openai", model="gpt-5.4")
    )
    try:
        manager.start()
        with (
            patch(
                "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
            ),
            patch.object(session_titles, "generate_title", gated_generate),
        ):
            manager.submit_saved_session_input(session_id, text=text)
            if rename:
                manager.update_session_title(session_id, "My own name")
            release.set()
            for thread in threading.enumerate():
                if thread.name == "pbi-agent-web-session-title":
                    thread.join(timeout=10)
        with SessionStore(db_path=db_path) as store:
            record = store.get_session(session_id)
    finally:
        manager.shutdown()
    assert record is not None
    return record.title


@pytest.mark.usefixtures("ready_assets")
def test_first_message_title_is_replaced_by_generated_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = _submit_first_message(tmp_path, monkeypatch, "please fix the login bug")
    assert title == "Generated title"


@pytest.mark.usefixtures("ready_assets")
def test_generated_title_does_not_overwrite_manual_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = _submit_first_message(
        tmp_path, monkeypatch, "please fix the login bug", rename=True
    )
    assert title == "My own name"


def test_replace_session_title_only_replaces_expected_title(tmp_path: Path) -> None:
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "gpt-5.4", "draft")
        # Simulates a manual rename landing between read and conditional write.
        store.update_session(session_id, title="My own name")
        assert not store.replace_session_title(
            session_id, expected="draft", title="Generated title"
        )
        assert store.replace_session_title(
            session_id, expected="My own name", title="Generated title"
        )
        record = store.get_session(session_id)
    assert record is not None
    assert record.title == "Generated title"


def test_first_message_title_stays_truncated_without_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = _submit_first_message(tmp_path, monkeypatch, "please fix the login bug")
    assert title == "please fix the login bug"


@pytest.mark.usefixtures("ready_assets")
def test_slash_command_title_is_not_sent_to_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _submit_first_message(tmp_path, monkeypatch, "/compact") == "/compact"


def test_web_app_startup_fetches_title_assets_in_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from pbi_agent.config import Settings
    from pbi_agent.web.serve import create_app

    monkeypatch.chdir(tmp_path)
    called = threading.Event()
    monkeypatch.setattr(session_titles, "ensure_assets", called.set)

    app = create_app(Settings(api_key="test-key", provider="openai", model="gpt-5.4"))
    with TestClient(app):
        assert called.wait(timeout=5)
