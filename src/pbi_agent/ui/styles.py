"""Shared styling for the Textual chat app."""

CHAT_APP_CSS = """
Screen {
    background: $surface;
}

/* ---- chat log ---- */
#chat-log {
    height: 1fr;
    padding: 0 1 1 1;
}

#status-row {
    height: auto;
    min-height: 0;
}

/* ---- welcome ---- */
WelcomeBanner {
    text-align: center;
    padding: 1 2;
    margin: 1 6;
    border: tall #F2C811;
    background: $boost;
}

/* ---- user message ---- */
UserMessage {
    margin: 1 1 1 12;
    padding: 1 2;
    background: $primary 15%;
    border-left: thick $success;
}

/* ---- assistant response ---- */
AssistantMarkdown {
    margin: 1 12 0 1;
    padding: 0 2;
}

/* ---- waiting ---- */
WaitingIndicator {
    margin: 0 12 0 1;
    padding: 0 2;
    height: auto;
}
WaitingIndicator > .waiting-spinner {
    color: $accent;
}
WaitingIndicator > .waiting-message {
    color: $text-muted;
}

/* ---- tool groups ---- */
ToolGroup {
    margin: 0 4;
    padding: 0 0;
    height: auto;
    background: $boost;
    border: none;
    border-left: thick #6B7280;
}
ToolGroup.tool-group-generic {
    border-left: thick #6B7280;
}
ToolGroup.tool-group-mixed {
    border-left: thick #8B5CF6;
}
ToolGroup.tool-group-shell {
    border-left: thick #3B82F6;
}
ToolGroup.tool-group-apply-patch {
    border-left: thick #F97316;
}
ToolGroup.tool-group-skill-knowledge {
    border-left: thick #22C55E;
}
ToolGroup.tool-group-init-report {
    border-left: thick #06B6D4;
}
ToolGroup.tool-group-list-files {
    border-left: thick #818CF8;
}
ToolGroup.tool-group-search-files {
    border-left: thick #EC4899;
}
ToolGroup.tool-group-read-file {
    border-left: thick #EAB308;
}
ToolGroup > CollapsibleTitle {
    padding: 1 2;
    color: $text-muted;
}
ToolGroup > Contents {
    padding: 0 2;
}
ToolItem {
    background: $surface;
    border: none;
    padding-left: 2;
    margin: 0 0 1 0;
}
ToolItem.tool-call-generic {
    background: #6B7280 10%;
}
ToolItem.tool-call-shell {
    background: #3B82F6 14%;
}
ToolItem.tool-call-apply-patch {
    background: #F97316 14%;
}
ToolItem.tool-call-skill-knowledge {
    background: #22C55E 14%;
}
ToolItem.tool-call-init-report {
    background: #06B6D4 14%;
}
ToolItem.tool-call-list-files {
    background: #818CF8 14%;
}
ToolItem.tool-call-search-files {
    background: #EC4899 14%;
}
ToolItem.tool-call-read-file {
    background: #EAB308 14%;
}

/* ---- thinking block ---- */
ThinkingBlock {
    margin: 0 4;
    padding: 0 0;
    height: auto;
    background: $boost;
    border: none;
    border-left: thick #64748B;
}
ThinkingBlock > CollapsibleTitle {
    padding: 1 2;
    color: $text-muted;
}
ThinkingBlock > Contents {
    padding: 0 2;
}
ThinkingContent {
    color: $text-muted;
    padding: 0 1;
}

/* ---- usage summary ---- */
UsageSummary {
    text-align: center;
    color: $text-muted;
    margin: 0 4;
    padding: 1 2;
    background: $boost;
    border: none;
    border-left: thick $primary;
}

/* ---- error / notice ---- */
ErrorMessage {
    color: $error;
    text-style: bold;
    margin: 0 4;
    padding: 1 2;
    background: $boost;
    border: none;
    border-left: thick $error;
}
NoticeMessage {
    color: $warning;
    margin: 0 4;
    padding: 1 2;
    background: $boost;
    border: none;
    border-left: thick $warning;
}
.debug-msg {
    color: $text-muted;
    margin: 0 4;
}

/* ---- input ---- */
#input-row {
    dock: bottom;
    margin: 1 2 1 2;
    height: auto;
    align-vertical: middle;
}
#user-input {
    width: 1fr;
    min-width: 0;
    height: 3;
}
#user-input:disabled {
    opacity: 0.5;
}
#send-button {
    width: auto;
    min-width: 10;
    height: 3;
    margin: 0 5 0 0;
}
#send-button:disabled {
    opacity: 0.5;
}
"""


__all__ = ["CHAT_APP_CSS"]
