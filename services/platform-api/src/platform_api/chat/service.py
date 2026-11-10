"""Service: chats, messages and the event stream.

send: check the user -> one run at a time -> save the user message -> start an agent run (agent module)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from platform_api.access.schemas import AccessCheck
from platform_api.agent.schemas import RunNotAllowed, RunRejected, Runs
from platform_api.chat.models import (
    NEW_CHAT_TITLE, Chat, ChatMessage, ChatStatus, InvalidChat, check_runner_event, message_from_event, user_text,
)
from platform_api.chat.schemas import (
    ChatBusy, ChatEventSink, ChatNotAllowed, ChatNotFound, ChatRejected, Chats, ChatSummaryView, ChatView, EventView,
    RunnerChat, RunnerContext, Sent,
)
from platform_api.chat.interfaces import ChatRepository

USE_CHAT = "chat.use"
_END_STATUS = {"finished": ChatStatus.WAITING, "cancelled": ChatStatus.WAITING,
               "failed": ChatStatus.FAILED, "expired": ChatStatus.FAILED}


def _summary(c: Chat) -> ChatSummaryView:
    return ChatSummaryView(c.id, c.system, c.env, c.title, c.status.value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatService(Chats, ChatEventSink, RunnerChat):
    def __init__(self, chats: ChatRepository, runs: Runs, access: AccessCheck,
                 clock: Callable[[], datetime] = _utcnow,
                 new_id: Callable[[str], str] = lambda prefix: prefix + secrets.token_hex(6)) -> None:
        self._chats, self._runs, self._access, self._clock, self._new_id = chats, runs, access, clock, new_id

    # ---- Chats (web app) ----

    def create(self, user_id: str, system: str, env: str = "dev") -> ChatView:
        self._allowed(user_id)
        try:
            chat = Chat(self._new_id("c_"), system, env, NEW_CHAT_TITLE, ChatStatus.WAITING, user_id, self._clock())
        except InvalidChat as e:
            raise ChatRejected(str(e)) from e
        self._chats.add(chat)
        return self._view(chat)

    def list(self, user_id: str, system: str) -> list[ChatSummaryView]:
        self._allowed(user_id)
        return [_summary(c) for c in self._chats.list(system)]

    def get(self, user_id: str, chat_id: str) -> ChatView:
        self._allowed(user_id)
        return self._view(self._find(chat_id))

    def send(self, user_id: str, chat_id: str, text: str) -> Sent:
        self._allowed(user_id)
        chat = self._find(chat_id)
        if chat.busy:
            raise ChatBusy("the agent is still working on the previous message")
        try:
            text = user_text(text)
        except InvalidChat as e:
            raise ChatRejected(str(e)) from e
        after = self._chats.last_seq(chat_id)
        message_id = self._new_id("m_")
        self._chats.record(chat_id, {"type": "message", "message": {"id": message_id, "role": "user", "text": text}},
                           ChatMessage(chat_id, message_id, "user", {"id": message_id, "role": "user", "text": text}))
        try:
            run = self._runs.start(user_id, chat_id, chat.system, chat.env)
        except (RunNotAllowed, RunRejected) as e:
            self._fail(chat, f"The agent could not start: {e}")
            return Sent(message_id, after, "failed")
        if run.status != "running":
            self._fail(chat, f"The agent could not start: {run.error or run.status}")
            return Sent(message_id, after, "failed")
        started = chat.run_started(run.run_id, text)
        self._chats.record(chat_id, {"type": "status", "status": started.status.value}, chat=started)
        return Sent(message_id, after, "running")

    def events_after(self, user_id: str, chat_id: str, after_seq: int, limit: int = 200) -> list[EventView]:
        self._allowed(user_id)
        self._find(chat_id)
        return [EventView(seq, body) for seq, body in self._chats.events_after(chat_id, after_seq, min(limit, 500))]

    # ---- ChatEventSink (approval module, wiring) ----

    def publish(self, chat_id: str, event: dict[str, Any]) -> int:
        chat = self._find(chat_id)
        try:
            message = message_from_event(chat_id, event)
        except InvalidChat as e:
            raise ChatRejected(str(e)) from e
        updated = chat.with_status(ChatStatus(event["status"])) if event.get("type") == "status" else None
        return self._chats.record(chat_id, event, message, updated)

    # ---- RunnerChat (agent containers) ----

    def context(self, chat_id: str) -> RunnerContext:
        chat = self._find(chat_id)
        history = [{"role": "user" if m.role == "user" else "assistant", "text": str(m.body.get("text", ""))}
                   for m in self._chats.messages(chat_id) if m.role in ("user", "agent") and m.body.get("text")]
        return RunnerContext(chat.id, chat.system, chat.env, history)

    def runner_event(self, chat_id: str, event: dict[str, Any]) -> int:
        try:
            event = check_runner_event(event)
        except InvalidChat as e:
            raise ChatRejected(str(e)) from e
        return self.publish(chat_id, event)

    def run_ended(self, chat_id: str, run_id: str, status: str, error: str | None) -> None:
        chat = self._chats.get(chat_id)
        if chat is None or chat.active_run_id != run_id:
            return  # an old run, or the chat is gone
        if status in ("failed", "expired"):
            text = f"The agent stopped: {error or status}."
            mid = self._new_id("m_")
            self._chats.record(chat_id, {"type": "message", "message": {"id": mid, "role": "agent", "text": text}},
                               ChatMessage(chat_id, mid, "agent", {"id": mid, "role": "agent", "text": text}))
        ended = chat.run_ended(_END_STATUS.get(status, ChatStatus.WAITING))
        self._chats.record(chat_id, {"type": "status", "status": ended.status.value}, chat=ended)

    # ---- helpers ----

    def _fail(self, chat: Chat, text: str) -> None:
        mid = self._new_id("m_")
        self._chats.record(chat.id, {"type": "message", "message": {"id": mid, "role": "agent", "text": text}},
                           ChatMessage(chat.id, mid, "agent", {"id": mid, "role": "agent", "text": text}))
        failed = chat.with_status(ChatStatus.FAILED)
        self._chats.record(chat.id, {"type": "status", "status": "failed"}, chat=failed)

    def _allowed(self, user_id: str) -> None:
        if not self._access.can(user_id, USE_CHAT):
            raise ChatNotAllowed(f"{user_id!r} may not use chats (needs {USE_CHAT})")

    def _find(self, chat_id: str) -> Chat:
        chat = self._chats.get(chat_id)
        if chat is None:
            raise ChatNotFound(chat_id)
        return chat

    def _view(self, chat: Chat) -> ChatView:
        return ChatView(chat.id, chat.system, chat.env, chat.title, chat.status.value,
                        [m.body for m in self._chats.messages(chat.id)], self._chats.last_seq(chat.id))
