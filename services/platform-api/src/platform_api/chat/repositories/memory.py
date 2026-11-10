"""Chats in memory (tests, quick local runs without a database)."""

from __future__ import annotations

import itertools
import threading
from typing import Any

from platform_api.chat.models import Chat, ChatMessage
from platform_api.chat.interfaces import ChatRepository


class InMemoryChatRepository(ChatRepository):
    def __init__(self) -> None:
        self._chats: dict[str, Chat] = {}
        self._messages: dict[str, dict[str, ChatMessage]] = {}  # dicts keep first-insert order
        self._events: list[tuple[int, str, dict[str, Any]]] = []
        self._seq = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, chat: Chat) -> None:
        with self._lock:
            self._chats[chat.id] = chat
            self._messages[chat.id] = {}

    def get(self, chat_id: str) -> Chat | None:
        return self._chats.get(chat_id)

    def list(self, system: str) -> list[Chat]:
        return sorted((c for c in self._chats.values() if c.system == system), key=lambda c: c.created_at, reverse=True)

    def messages(self, chat_id: str) -> list[ChatMessage]:
        return list(self._messages.get(chat_id, {}).values())

    def record(self, chat_id: str, event: dict[str, Any], message: ChatMessage | None = None,
               chat: Chat | None = None) -> int:
        with self._lock:
            seq = next(self._seq)
            self._events.append((seq, chat_id, event))
            if message is not None:
                self._messages[chat_id][message.id] = message
            if chat is not None:
                self._chats[chat.id] = chat
            return seq

    def events_after(self, chat_id: str, after_seq: int, limit: int) -> list[tuple[int, dict[str, Any]]]:
        return [(s, e) for s, c, e in self._events if c == chat_id and s > after_seq][:limit]

    def last_seq(self, chat_id: str) -> int:
        return max((s for s, c, _ in self._events if c == chat_id), default=0)
