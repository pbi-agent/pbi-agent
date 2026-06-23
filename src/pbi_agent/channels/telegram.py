from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pbi_agent.agent.session.shared import NEW_COMMAND
from pbi_agent.config import ResolvedRuntime
from pbi_agent.display.protocol import (
    PendingToolCall,
    PendingUserQuestion,
    QueuedInput,
    QueuedRuntimeChange,
    UserQuestionAnswer,
)
from pbi_agent.media import load_image_bytes
from pbi_agent.models.messages import (
    ImageAttachment,
    TokenUsage,
    WebSearchSource,
)
from pbi_agent.session_store import MessageImageAttachment, MessageRecord, SessionStore
from pbi_agent.task_runner import run_single_turn_in_directory
from pbi_agent.channels.types import ChannelRuntimeStatus, TelegramChannelConfig

TELEGRAM_PLATFORM = "telegram"
TELEGRAM_MESSAGE_LIMIT_UTF16 = 4096
DEFAULT_IMAGE_PROMPT = "Please analyze the attached image."


@dataclass(frozen=True, slots=True)
class _TokenLease:
    owner_id: str
    runner_id: str


_TOKEN_LEASES: dict[str, _TokenLease] = {}
_TOKEN_LEASE_LOCK = threading.Lock()


@dataclass(slots=True)
class TelegramAttachment:
    file_id: str
    name: str
    mime_type: str


@dataclass(slots=True)
class TelegramInboundMessage:
    update_id: int
    chat_id: str
    message_id: int
    source_key: str
    title: str
    text: str
    user_id: str | None = None
    thread_id: int | None = None
    attachments: list[TelegramAttachment] = field(default_factory=list)


class TelegramApiError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout
        self._api_base = f"https://api.telegram.org/bot{token}"
        self._file_base = f"https://api.telegram.org/file/bot{token}"

    def get_updates(
        self, *, offset: int | None, timeout: int = 20
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "edited_message", "channel_post"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._request("getUpdates", payload, timeout=timeout + 5)
        return (
            [item for item in result if isinstance(item, dict)]
            if isinstance(result, list)
            else []
        )

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        thread_id: int | None = None,
    ) -> None:
        for chunk in split_telegram_text(text):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if thread_id is not None:
                payload["message_thread_id"] = thread_id
            self._request("sendMessage", payload)

    def send_chat_action(self, *, chat_id: str, thread_id: int | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "action": "typing"}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        self._request("sendChatAction", payload)

    def set_reaction(self, *, chat_id: str, message_id: int) -> None:
        self._request(
            "setMessageReaction",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": "👀"}],
            },
        )

    def get_file(self, file_id: str) -> str:
        result = self._request("getFile", {"file_id": file_id})
        if not isinstance(result, dict) or not isinstance(result.get("file_path"), str):
            raise TelegramApiError(
                "Telegram getFile response did not include file_path."
            )
        return result["file_path"]

    def download_file(self, file_path: str) -> bytes:
        url = f"{self._file_base}/{urllib.parse.quote(file_path, safe='/')}"
        with urllib.request.urlopen(url, timeout=self._timeout) as response:
            return response.read()

    def _request(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._api_base}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout or self._timeout,
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise TelegramApiError(str(exc)) from exc
        data = json.loads(raw)
        if not isinstance(data, dict) or not data.get("ok"):
            description = data.get("description") if isinstance(data, dict) else None
            raise TelegramApiError(str(description or "Telegram API request failed."))
        return data.get("result")


class TelegramDisplay:
    verbose = False

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.shutdown_requested = False

    def bind_session(self, session_id: str | None) -> None:
        self.session_id = session_id

    def request_shutdown(self) -> None:
        self.shutdown_requested = True

    def request_interrupt(
        self, *, item_id: str | None = None, input_text: str | None = None
    ) -> None:
        self.shutdown_requested = True

    def clear_interrupt(self) -> None:
        self.shutdown_requested = False

    def interrupt_requested(self) -> bool:
        return self.shutdown_requested

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images: list[ImageAttachment] | None = None,
        image_attachments: list[MessageImageAttachment] | None = None,
        interactive_mode: bool = False,
        include_tool_history: bool = False,
        item_id: str | None = None,
    ) -> None:
        return

    def request_new_session(self) -> None:
        return

    def ask_user_questions(
        self, questions: list[PendingUserQuestion]
    ) -> list[UserQuestionAnswer]:
        return [
            UserQuestionAnswer(
                question_id=item.question_id,
                question=item.question,
                answer="Telegram channel runs do not support interactive questions.",
            )
            for item in questions
        ]

    def reset_session(self) -> None:
        return

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> "TelegramDisplay":
        return TelegramDisplay()

    def finish_sub_agent(self, *, status: str) -> None:
        return

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        return

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange:
        return ""

    def assistant_start(self) -> None:
        return

    def assistant_stop(self) -> None:
        return

    def tool_execution_start(self, calls: list[PendingToolCall]) -> None:
        return

    def tool_execution_stop(self) -> None:
        return

    def wait_start(self, message: str = "model is processing your request...") -> None:
        return

    def wait_stop(self) -> None:
        return

    def render_user_message(self, text: str) -> None:
        return

    def render_markdown(self, text: str) -> None:
        return

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        return widget_id

    def render_redacted_thinking(self) -> None:
        return

    def session_usage(self, usage: TokenUsage) -> None:
        return

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        return

    def shell_start(self, commands: list[str]) -> None:
        return

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
        result: Any = None,
    ) -> None:
        return

    def patch_start(self, count: int) -> None:
        return

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
        diff: str = "",
        diff_line_numbers: list[dict[str, int | None]] | None = None,
        tool_name: str = "apply_patch",
        arguments: Any = None,
        result: Any = None,
    ) -> None:
        return

    def function_start(self, count: int) -> None:
        return

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
        result: Any = None,
    ) -> None:
        return

    def tool_group_end(self) -> None:
        return

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        return

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        return

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        return

    def error(self, message: str) -> None:
        return

    def debug(self, message: str) -> None:
        return

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        return

    def replay_history(self, messages: list[MessageRecord]) -> None:
        return


class TelegramChannelRunner:
    def __init__(
        self,
        *,
        runtime: ResolvedRuntime,
        workspace_root: Path,
        directory_key: str,
        config: TelegramChannelConfig,
        owner_id: str,
    ) -> None:
        self._runtime = runtime
        self._workspace_root = workspace_root
        self._directory_key = directory_key
        self._config = config
        self._owner_id = owner_id
        self._client = TelegramBotClient(resolve_telegram_token(config))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queues: dict[str, queue.Queue[TelegramInboundMessage | None]] = {}
        self._workers: dict[str, threading.Thread] = {}
        self._workers_guard = threading.Lock()
        self.status = ChannelRuntimeStatus("disabled")
        self._lease_key = token_fingerprint(resolve_telegram_token(config))
        self._lease_runner_id = uuid.uuid4().hex
        self._lease_released = False

    def start(self) -> ChannelRuntimeStatus:
        if not self._acquire_token_lease():
            self.status = ChannelRuntimeStatus(
                "error",
                "This Telegram bot token is already active in another workspace.",
            )
            _persist_status(self._directory_key, self.status)
            return self.status
        self.status = ChannelRuntimeStatus("running")
        _persist_status(self._directory_key, self.status)
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name=f"pbi-agent-telegram-{self._directory_key[:8]}",
        )
        self._thread.start()
        return self.status

    def stop(self) -> None:
        self._stop.set()
        self._stop_workers()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._join_workers(timeout=2.0)
        if self._all_threads_stopped():
            self._release_token_lease()
        if self.status.state == "running" and self._all_threads_stopped():
            self.status = ChannelRuntimeStatus("stopped")
            _persist_status(self._directory_key, self.status)

    def restart_with(self, config: TelegramChannelConfig) -> ChannelRuntimeStatus:
        self.stop()
        if not self._all_threads_stopped():
            self.status = ChannelRuntimeStatus(
                "error",
                "Telegram channel is still stopping; retry restart after current work exits.",
            )
            _persist_status(self._directory_key, self.status)
            return self.status
        self._config = config
        self._client = TelegramBotClient(resolve_telegram_token(config))
        self._lease_key = token_fingerprint(resolve_telegram_token(config))
        self._lease_runner_id = uuid.uuid4().hex
        self._stop = threading.Event()
        self._lease_released = False
        return self.start()

    def _poll_loop(self) -> None:
        try:
            next_offset = (
                self._config.last_update_id + 1
                if self._config.last_update_id is not None
                else None
            )
            while not self._stop.is_set():
                try:
                    updates = self._client.get_updates(offset=next_offset)
                    for update in updates:
                        update_id = int(update.get("update_id", 0))
                        if not self._handle_update(update):
                            break
                        next_offset = update_id + 1
                        with SessionStore() as store:
                            store.update_channel_config_fields(
                                self._directory_key,
                                TELEGRAM_PLATFORM,
                                {"last_update_id": update_id},
                            )
                except Exception as exc:
                    self.status = ChannelRuntimeStatus("error", str(exc))
                    _persist_status(self._directory_key, self.status)
                    if self._stop.wait(5.0):
                        break
        finally:
            self._release_token_lease_if_stopped(current_thread_stopping=True)

    def _handle_update(self, update: dict[str, Any]) -> bool:
        message = parse_telegram_update(update, self._config)
        if message is None:
            return True
        if not self._enqueue_turn(message):
            return False
        try:
            self._client.set_reaction(
                chat_id=message.chat_id,
                message_id=message.message_id,
            )
        except Exception:
            pass
        return True

    def _enqueue_turn(self, message: TelegramInboundMessage) -> bool:
        with self._workers_guard:
            if self._stop.is_set():
                return False
            source_queue = self._queues.get(message.source_key)
            worker = self._workers.get(message.source_key)
            if source_queue is None:
                source_queue = queue.Queue()
                self._queues[message.source_key] = source_queue
            if worker is None or not worker.is_alive():
                worker = threading.Thread(
                    target=self._source_worker,
                    args=(message.source_key, source_queue),
                    daemon=True,
                    name=(
                        f"pbi-agent-telegram-{self._directory_key[:8]}-"
                        f"{message.source_key}"
                    ),
                )
                self._workers[message.source_key] = worker
                worker.start()
            source_queue.put(message)
            return True

    def _source_worker(
        self,
        source_key: str,
        source_queue: queue.Queue[TelegramInboundMessage | None],
    ) -> None:
        try:
            while True:
                message = source_queue.get()
                try:
                    if message is None:
                        return
                    try:
                        self._run_turn(message)
                    except Exception:
                        self._send_turn_error(message)
                finally:
                    source_queue.task_done()
        finally:
            with self._workers_guard:
                if self._workers.get(source_key) is threading.current_thread():
                    del self._workers[source_key]
                if self._queues.get(source_key) is source_queue:
                    del self._queues[source_key]
            self._release_token_lease_if_stopped(current_thread_stopping=True)

    def _run_turn(self, message: TelegramInboundMessage) -> None:
        prompt = message.text.strip() or DEFAULT_IMAGE_PROMPT
        if _is_new_session_command(prompt):
            self._create_new_channel_session(message)
            return
        images: list[ImageAttachment] = []
        for attachment in message.attachments:
            try:
                file_path = self._client.get_file(attachment.file_id)
                raw = self._client.download_file(file_path)
                images.append(load_image_bytes(attachment.name, raw))
            except Exception as exc:
                self._client.send_message(
                    chat_id=message.chat_id,
                    thread_id=message.thread_id,
                    text=f"Could not read the attached image: {exc}",
                )
                return
        try:
            self._client.send_chat_action(
                chat_id=message.chat_id,
                thread_id=message.thread_id,
            )
        except Exception:
            pass
        settings = self._runtime.settings
        with SessionStore() as store:
            session_id = store.get_or_create_channel_session_mapping(
                directory=self._directory_key,
                platform=TELEGRAM_PLATFORM,
                source_key=message.source_key,
                provider=settings.provider,
                provider_id=self._runtime.provider_id,
                profile_id=self._runtime.profile_id,
                model=settings.model,
                title=message.title,
            )
        outcome = run_single_turn_in_directory(
            prompt,
            self._runtime,
            TelegramDisplay(),
            workspace_root=self._workspace_root,
            resume_session_id=session_id,
            images=images or None,
            workspace_directory_key=self._directory_key,
        )
        response = outcome.text.strip() or "(No response.)"
        self._client.send_message(
            chat_id=message.chat_id,
            thread_id=message.thread_id,
            text=response,
        )

    def _create_new_channel_session(self, message: TelegramInboundMessage) -> None:
        settings = self._runtime.settings
        with SessionStore() as store:
            store.create_channel_session_mapping(
                directory=self._directory_key,
                platform=TELEGRAM_PLATFORM,
                source_key=message.source_key,
                provider=settings.provider,
                provider_id=self._runtime.provider_id,
                profile_id=self._runtime.profile_id,
                model=settings.model,
                title=message.title,
            )
        self._client.send_message(
            chat_id=message.chat_id,
            thread_id=message.thread_id,
            text="Started a new conversation. Send your next message to continue here.",
        )

    def _send_turn_error(self, message: TelegramInboundMessage) -> None:
        try:
            self._client.send_message(
                chat_id=message.chat_id,
                thread_id=message.thread_id,
                text="Sorry, I couldn't process that Telegram message. Please try again.",
            )
        except Exception:
            pass

    def _stop_workers(self) -> None:
        with self._workers_guard:
            queues = list(self._queues.values())
            for source_queue in queues:
                source_queue.put(None)

    def _join_workers(self, *, timeout: float) -> None:
        with self._workers_guard:
            workers = list(self._workers.values())
        for worker in workers:
            if worker is threading.current_thread():
                continue
            worker.join(timeout=timeout)

    def _all_threads_stopped(self, *, current_thread_stopping: bool = False) -> bool:
        current_thread = threading.current_thread()
        if (
            self._thread is not None
            and self._thread.is_alive()
            and not (current_thread_stopping and self._thread is current_thread)
        ):
            return False
        with self._workers_guard:
            return not any(
                worker.is_alive()
                and not (current_thread_stopping and worker is current_thread)
                for worker in self._workers.values()
            )

    def _release_token_lease_if_stopped(
        self, *, current_thread_stopping: bool = False
    ) -> None:
        if self._stop.is_set() and self._all_threads_stopped(
            current_thread_stopping=current_thread_stopping
        ):
            self._release_token_lease()
            if self.status.state == "running":
                self.status = ChannelRuntimeStatus("stopped")
                _persist_status(self._directory_key, self.status)

    def _acquire_token_lease(self) -> bool:
        with _TOKEN_LEASE_LOCK:
            if _TOKEN_LEASES.get(self._lease_key) is not None:
                return False
            _TOKEN_LEASES[self._lease_key] = _TokenLease(
                owner_id=self._owner_id,
                runner_id=self._lease_runner_id,
            )
            self._lease_released = False
            return True

    def _release_token_lease(self) -> None:
        with _TOKEN_LEASE_LOCK:
            if self._lease_released:
                return
            current = _TOKEN_LEASES.get(self._lease_key)
            if current == _TokenLease(
                owner_id=self._owner_id,
                runner_id=self._lease_runner_id,
            ):
                del _TOKEN_LEASES[self._lease_key]
            self._lease_released = True


def parse_telegram_update(
    update: dict[str, Any],
    config: TelegramChannelConfig,
) -> TelegramInboundMessage | None:
    raw_message = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
    )
    if not isinstance(raw_message, dict):
        return None
    chat = raw_message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = str(chat.get("id") or "")
    chat_type = str(chat.get("type") or "")
    user = raw_message.get("from")
    user_id = str(user.get("id")) if isinstance(user, dict) and user.get("id") else None
    if isinstance(user, dict) and user.get("is_bot"):
        return None
    if not _allowed(config, chat_type=chat_type, chat_id=chat_id, user_id=user_id):
        return None
    text = str(raw_message.get("text") or raw_message.get("caption") or "")
    attachments = _image_attachments(raw_message)
    if not text.strip() and not attachments:
        return None
    message_id = raw_message.get("message_id")
    if not isinstance(message_id, int):
        return None
    thread_id = raw_message.get("message_thread_id")
    thread_id = thread_id if isinstance(thread_id, int) else None
    source_key = _source_key(chat_type, chat_id, user_id, thread_id)
    title = f"Telegram {source_key}"
    return TelegramInboundMessage(
        update_id=int(update.get("update_id", 0)),
        chat_id=chat_id,
        message_id=message_id,
        source_key=source_key,
        title=title,
        text=text,
        user_id=user_id,
        thread_id=thread_id,
        attachments=attachments,
    )


def split_telegram_text(text: str) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    current = ""
    current_units = 0
    for char in text:
        units = len(char.encode("utf-16-le")) // 2
        if current and current_units + units > TELEGRAM_MESSAGE_LIMIT_UTF16:
            chunks.append(current)
            current = char
            current_units = units
        else:
            current += char
            current_units += units
    if current:
        chunks.append(current)
    return chunks


def _is_new_session_command(text: str) -> bool:
    return " ".join(text.strip().lower().split()) == NEW_COMMAND


def resolve_telegram_token(config: TelegramChannelConfig) -> str:
    if config.token_source == "secret":
        token = config.token_secret or ""
    else:
        token = os.environ.get(config.token_env_var, "")
    if not token.strip():
        raise ValueError("Telegram bot token is missing.")
    return token.strip()


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _allowed(
    config: TelegramChannelConfig,
    *,
    chat_type: str,
    chat_id: str,
    user_id: str | None,
) -> bool:
    allowed_users = set(config.allowed_users)
    allowed_chats = set(config.allowed_chats)
    if chat_type == "private":
        return bool(user_id and user_id in allowed_users)
    return chat_id in allowed_chats


def _source_key(
    chat_type: str,
    chat_id: str,
    user_id: str | None,
    thread_id: int | None,
) -> str:
    if chat_type == "private" and user_id:
        return f"dm:{user_id}"
    if chat_type == "channel":
        return f"channel:{chat_id}"
    if thread_id is not None:
        return f"chat:{chat_id}:topic:{thread_id}"
    return f"chat:{chat_id}"


def _image_attachments(message: dict[str, Any]) -> list[TelegramAttachment]:
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        candidates = [item for item in photo if isinstance(item, dict)]
        if candidates:
            best = max(candidates, key=lambda item: int(item.get("file_size") or 0))
            file_id = best.get("file_id")
            if isinstance(file_id, str):
                return [
                    TelegramAttachment(
                        file_id=file_id,
                        name=f"telegram-{file_id}.jpg",
                        mime_type="image/jpeg",
                    )
                ]
    document = message.get("document")
    if isinstance(document, dict):
        mime_type = str(document.get("mime_type") or "")
        file_id = document.get("file_id")
        if mime_type.startswith("image/") and isinstance(file_id, str):
            return [
                TelegramAttachment(
                    file_id=file_id,
                    name=str(document.get("file_name") or f"telegram-{file_id}"),
                    mime_type=mime_type,
                )
            ]
    return []


def _persist_status(directory_key: str, status: ChannelRuntimeStatus) -> None:
    with SessionStore() as store:
        store.set_channel_status(
            directory_key,
            TELEGRAM_PLATFORM,
            status=status.state,
            error=status.error,
        )
