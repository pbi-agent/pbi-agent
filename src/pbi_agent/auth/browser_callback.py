from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, cast
from urllib.parse import parse_qs, urlparse

_BROWSER_CALLBACK_PATH = "/auth/callback"
_DEFAULT_CALLBACK_PORT = 1455
_CALLBACK_SERVER_HOST = "127.0.0.1"
_SUCCESS_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>PBI Agent Authorization Complete</title></head>
  <body>
    <h1>Authorization complete</h1>
    <p>You can close this window and return to pbi-agent.</p>
    <script>setTimeout(() => window.close(), 1500)</script>
  </body>
</html>
"""
_ERROR_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>PBI Agent Authorization Failed</title></head>
  <body>
    <h1>Authorization failed</h1>
    <p>{message}</p>
  </body>
</html>
"""


@dataclass(slots=True)
class BrowserAuthCallbackParams:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    error_description: str | None = None


@dataclass(slots=True)
class BrowserAuthCallbackOutcome:
    completed: bool
    error_message: str | None = None


class _BrowserCallbackServer(ThreadingHTTPServer):
    def __init__(
        self,
        *,
        callback_handler: Callable[
            [BrowserAuthCallbackParams], BrowserAuthCallbackOutcome
        ],
        port: int,
    ) -> None:
        super().__init__((_CALLBACK_SERVER_HOST, port), _BrowserCallbackHandler)
        self.callback_handler = callback_handler
        self.callback_path = _BROWSER_CALLBACK_PATH


class _BrowserCallbackHandler(BaseHTTPRequestHandler):
    server: _BrowserCallbackServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self._send_html(404, _ERROR_HTML.format(message="Unknown callback path."))
            return

        params = parse_qs(parsed.query)
        try:
            outcome = self.server.callback_handler(
                BrowserAuthCallbackParams(
                    code=_first_query_value(params, "code"),
                    state=_first_query_value(params, "state"),
                    error=_first_query_value(params, "error"),
                    error_description=_first_query_value(
                        params, "error_description"
                    ),
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._send_html(400, _ERROR_HTML.format(message=str(exc)))
            return

        if outcome.completed:
            self._send_html(200, _SUCCESS_HTML)
            return
        self._send_html(
            400,
            _ERROR_HTML.format(message=outcome.error_message or "Authorization failed."),
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        del format, args

    def _send_html(self, status_code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class BrowserAuthCallbackListener:
    def __init__(
        self,
        *,
        callback_handler: Callable[
            [BrowserAuthCallbackParams], BrowserAuthCallbackOutcome
        ],
    ) -> None:
        self._server = _create_callback_server(callback_handler=callback_handler)
        self._thread: threading.Thread | None = None

    @property
    def callback_url(self) -> str:
        host, port = cast(tuple[str, int], self._server.server_address)
        del host
        return f"http://localhost:{port}{self._server.callback_path}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="pbi-agent-auth-browser-callback",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        thread = self._thread
        self._thread = None
        self._server.shutdown()
        self._server.server_close()
        if thread is not None:
            thread.join(timeout=1.0)


def create_browser_auth_callback_listener(
    *,
    callback_handler: Callable[[BrowserAuthCallbackParams], BrowserAuthCallbackOutcome],
) -> BrowserAuthCallbackListener:
    return BrowserAuthCallbackListener(callback_handler=callback_handler)


def _create_callback_server(
    *,
    callback_handler: Callable[[BrowserAuthCallbackParams], BrowserAuthCallbackOutcome],
) -> _BrowserCallbackServer:
    try:
        return _BrowserCallbackServer(
            callback_handler=callback_handler,
            port=_DEFAULT_CALLBACK_PORT,
        )
    except OSError:
        return _BrowserCallbackServer(callback_handler=callback_handler, port=0)


def _first_query_value(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None
