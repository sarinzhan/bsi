"""What the chat module offers. Message and event bodies follow the web app's contract (web/src/api/types.ts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatSummaryView:
    id: str
    system: str
    env: str
    title: str
    status: str


@dataclass(frozen=True)
class ChatView(ChatSummaryView):
    messages: list[dict[str, Any]]
    last_seq: int  # stream events after this one to stay up to date


@dataclass(frozen=True)
class EventView:
    seq: int
    body: dict[str, Any]


@dataclass(frozen=True)
class Sent:
    message_id: str
    after_seq: int  # stream from here: the first event is the user's own message
    run_status: str  # running, or failed when the agent could not start


@dataclass(frozen=True)
class RunnerContext:
    """What an agent container gets: where it works and the conversation so far."""

    chat_id: str
    system: str
    env: str
    messages: list[dict[str, str]]  # [{"role": "user" | "assistant", "text": ...}], oldest first


class ChatNotFound(LookupError):
    pass


class ChatNotAllowed(PermissionError):
    pass


class ChatBusy(RuntimeError):
    """The agent is still working on the previous message."""


class ChatRejected(ValueError):
    pass


class Chats(Protocol):
    """The web app."""

    def create(self, user_id: str, system: str, env: str = "dev") -> ChatView: ...

    def list(self, user_id: str, system: str) -> list[ChatSummaryView]: ...

    def get(self, user_id: str, chat_id: str) -> ChatView: ...

    def send(self, user_id: str, chat_id: str, text: str) -> Sent: ...

    def events_after(self, user_id: str, chat_id: str, after_seq: int, limit: int = 200) -> list[EventView]: ...


class ChatEventSink(Protocol):
    """Other modules (approval) and the wiring (run ends) post events into a chat."""

    def publish(self, chat_id: str, event: dict[str, Any]) -> int: ...  # -> seq; raises ChatNotFound


class RunnerChat(Protocol):
    """Agent containers, through /runner (their run token tells which chat)."""

    def context(self, chat_id: str) -> RunnerContext: ...

    def runner_event(self, chat_id: str, event: dict[str, Any]) -> int: ...

    def run_ended(self, chat_id: str, run_id: str, status: str, error: str | None) -> None: ...
