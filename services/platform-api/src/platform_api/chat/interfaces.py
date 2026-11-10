"""What the chat module needs."""

from __future__ import annotations

from typing import Any, Protocol

from platform_api.chat.models import Chat, ChatMessage


class ChatRepository(Protocol):
    def add(self, chat: Chat) -> None: ...

    def get(self, chat_id: str) -> Chat | None: ...

    def list(self, system: str) -> list[Chat]: ...  # newest first

    def messages(self, chat_id: str) -> list[ChatMessage]: ...  # in the order they first appeared

    def record(self, chat_id: str, event: dict[str, Any], message: ChatMessage | None = None,
               chat: Chat | None = None) -> int:
        """In one transaction: append the event, upsert the message, save the chat. Returns the event's seq."""
        ...

    def events_after(self, chat_id: str, after_seq: int, limit: int) -> list[tuple[int, dict[str, Any]]]: ...

    def last_seq(self, chat_id: str) -> int: ...
