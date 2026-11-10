"""Chat: a conversation in one system and environment. Messages and events use the web app's contract
(web/src/api/types.ts: Message, AgentEvent), so the browser can apply them as they are.

- A message is upserted by id: a tool call card goes waiting -> running -> done by re-sending the same id.
- Every change is also an event with a sequence number; the browser streams events after the last one it saw.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

_SYSTEM = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ENVS = frozenset({"dev", "stage", "prod"})
MAX_TEXT = 20_000
NEW_CHAT_TITLE = "New chat"


class ChatStatus(str, Enum):
    WORKING = "working"  # the agent is busy
    WAITING = "waiting"  # waiting for a person: an approval, or the next message
    FAILED = "failed"  # the last run failed


class InvalidChat(ValueError):
    pass


@dataclass(frozen=True)
class Chat:
    id: str
    system: str
    env: str
    title: str
    status: ChatStatus
    created_by: str
    created_at: datetime
    active_run_id: str | None = None  # one agent run at a time per chat

    def __post_init__(self) -> None:
        if not _ID.match(self.id):
            raise InvalidChat(f"bad chat id {self.id!r}")
        if not _SYSTEM.match(self.system):
            raise InvalidChat(f"bad system name {self.system!r}")
        if self.env not in ENVS:
            raise InvalidChat(f"env must be one of {', '.join(sorted(ENVS))}")

    @property
    def busy(self) -> bool:
        return self.active_run_id is not None

    def with_status(self, status: ChatStatus) -> "Chat":
        return replace(self, status=status)

    def run_started(self, run_id: str, first_text: str) -> "Chat":
        title = self.title if self.title != NEW_CHAT_TITLE else _short(first_text)
        return replace(self, active_run_id=run_id, status=ChatStatus.WORKING, title=title)

    def run_ended(self, status: ChatStatus) -> "Chat":
        return replace(self, active_run_id=None, status=status)


@dataclass(frozen=True)
class ChatMessage:
    """One message as the web app shows it: {"id", "role": "user" | "agent" | "tool", ...}."""

    chat_id: str
    id: str
    role: str
    body: dict[str, Any]


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 40 else text[:40] + "…"


def user_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise InvalidChat("write a message first")
    if len(text) > MAX_TEXT:
        raise InvalidChat(f"messages are limited to {MAX_TEXT} characters")
    return text


def message_from_event(chat_id: str, event: dict[str, Any]) -> ChatMessage | None:
    """The message an event creates or updates, if any."""
    if event.get("type") != "message":
        return None
    m = event.get("message") or {}
    if not isinstance(m.get("id"), str) or not _ID.match(m["id"]) or m.get("role") not in ("user", "agent", "tool"):
        raise InvalidChat("a message needs an id and a role (user, agent, tool)")
    return ChatMessage(chat_id, m["id"], m["role"], m)


def check_runner_event(event: dict[str, Any]) -> dict[str, Any]:
    """What an agent container may post: its own text messages and steps. Never user messages or tool cards
    (tool cards come from the approval module, which knows what really ran)."""
    kind = event.get("type")
    if kind == "message":
        m = event.get("message") or {}
        if m.get("role") != "agent" or not isinstance(m.get("text"), str):
            raise InvalidChat("the agent may only post its own text messages")
        if len(m["text"]) > 50_000:
            raise InvalidChat("agent message too long")
        message_from_event("x", event)
        return {"type": "message", "message": {k: m[k] for k in ("id", "role", "text", "skills", "plan", "steps") if k in m}}
    if kind == "step":
        step = event.get("step") or {}
        if not isinstance(event.get("messageId"), str) or step.get("status") not in ("pending", "running", "done", "failed"):
            raise InvalidChat("a step needs messageId and step {id, text, status}")
        return {"type": "step", "messageId": event["messageId"],
                "step": {"id": str(step.get("id")), "text": str(step.get("text", ""))[:500], "status": step["status"]}}
    raise InvalidChat(f"agent containers cannot post {kind!r} events")
