"""Custom Textual web driver for browser-mode input parity."""

from __future__ import annotations

from textual import events
from textual.drivers.web_driver import WebDriver


class PBIWebDriver(WebDriver):
    """Web driver with chat-friendly keyboard and paste handling."""

    def start_application_mode(self) -> None:
        super().start_application_mode()
        # Match CLI drivers so modified Enter can be represented via CSI-u.
        self.write("\x1b[>1u")
        self.flush()

    def stop_application_mode(self) -> None:
        # Disable kitty keyboard protocol before leaving application mode.
        self.write("\x1b[<u")
        self.flush()
        super().stop_application_mode()

    def on_meta(self, packet_type: str, payload: dict[str, object]) -> None:
        if packet_type == "paste":
            text = payload.get("text", "")
            if isinstance(text, str):
                self._app.post_message(events.Paste(text))
            return
        super().on_meta(packet_type, payload)
