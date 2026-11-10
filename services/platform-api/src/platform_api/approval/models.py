"""Approval: a person decides whether one server tool call may run.

- read tools: "allow for this chat" grants all later reads on that server in this chat (still shown).
- write tools and ssh_exec: approved every time.
- No answer in time = denied. Nothing is ever allowed by default.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"
    EXPIRED = "expired"


class Answer(str, Enum):
    ALLOW_CHAT = "allow_chat"
    ALLOW_ONCE = "allow_once"
    DENY = "deny"


KINDS = frozenset({"read", "write", "full"})
AUTO = "auto · reads on this server allowed for this chat"
TIMEOUT = "no answer in 5 minutes"


class InvalidApproval(ValueError):
    pass


@dataclass(frozen=True)
class Approval:
    id: str
    run_id: str
    chat_id: str
    tool: str
    kind: str
    server: str
    command: str  # masked, exactly as the tools module will run it
    reason: str | None
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None = None  # user id, or None for auto/timeout
    note: str | None = None  # what the card shows after the decision, e.g. "Sarinzha K. · once"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise InvalidApproval(f"unknown tool kind {self.kind!r}")

    @property
    def pending(self) -> bool:
        return self.status is ApprovalStatus.PENDING

    def grants_reads_for_chat(self, answer: Answer) -> bool:
        return answer is Answer.ALLOW_CHAT and self.kind == "read"

    def decided(self, answer: Answer, user_id: str, user_name: str) -> "Approval":
        if not self.pending:
            raise InvalidApproval(f"already {self.status.value}")
        if answer is Answer.DENY:
            return replace(self, status=ApprovalStatus.DENIED, decided_by=user_id, note=user_name)
        how = "reads for this chat" if self.grants_reads_for_chat(answer) else "once"
        return replace(self, status=ApprovalStatus.ALLOWED, decided_by=user_id, note=f"{user_name} · {how}")

    def auto_allowed(self) -> "Approval":
        return replace(self, status=ApprovalStatus.ALLOWED, note=AUTO)

    def expired(self) -> "Approval":
        return replace(self, status=ApprovalStatus.EXPIRED, note=TIMEOUT)


def card(a: Approval, status: str, output: str | None = None) -> dict[str, Any]:
    """The tool call card, as the web app's ToolMessage (web/src/api/types.ts)."""
    call: dict[str, Any] = {"id": a.id, "tool": a.tool, "kind": a.kind, "server": a.server, "command": a.command,
                            "status": status}
    if a.reason:
        call["reason"] = a.reason
    if a.note:
        call["approvedBy"] = a.note
    if output is not None:
        call["output"] = output
    return {"type": "message", "message": {"id": a.id, "role": "tool", "call": call}}
