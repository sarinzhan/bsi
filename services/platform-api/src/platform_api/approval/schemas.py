"""What the approval module offers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    """From the tools module, before a tool runs."""

    run_id: str
    chat_id: str
    tool: str
    kind: str  # read | write | full
    server: str
    command: str
    reason: str | None


@dataclass(frozen=True)
class ApprovalOutcome:
    allowed: bool
    by: str
    call_id: str | None


class ApprovalNotFound(LookupError):
    pass


class ApprovalNotAllowed(PermissionError):
    pass


class ApprovalAlreadyDecided(RuntimeError):
    pass


class ToolApprovals(Protocol):
    """The tools module: ask (blocks until someone answers or the time is up), then report the outcome."""

    async def request(self, req: ApprovalRequest) -> ApprovalOutcome: ...

    def report(self, call_id: str, status: str, output: str) -> None: ...


class AnswerApprovals(Protocol):
    """The web app: a person clicks Allow / Allow for this chat / Deny on a card."""

    def answer(self, user_id: str, chat_id: str, call_id: str, answer: str) -> None: ...
