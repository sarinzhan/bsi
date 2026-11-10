"""Service: ask a person before a server tool runs, take their answer, show the outcome.

request (tools module, waits for a person):
  read tool + "allow for this chat" grant -> allowed at once, card shows "auto"
  otherwise -> card "waiting" in the chat -> wait for an answer (polled, so any process can answer)
  no answer in time -> denied
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from platform_api.access.schemas import AccessCheck
from platform_api.approval.models import Answer, Approval, ApprovalStatus, InvalidApproval, card
from platform_api.approval.schemas import (
    AnswerApprovals, ApprovalAlreadyDecided, ApprovalNotAllowed, ApprovalNotFound, ApprovalOutcome, ApprovalRequest,
    ToolApprovals,
)
from platform_api.approval.interfaces import ApprovalRepository
from platform_api.chat.schemas import ChatEventSink, ChatNotFound

TIMEOUT = timedelta(seconds=290)  # the tools service gives up at 300 s; answer before it does
POLL_S = 0.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalService(ToolApprovals, AnswerApprovals):
    def __init__(self, approvals: ApprovalRepository, chat: ChatEventSink, access: AccessCheck,
                 timeout: timedelta = TIMEOUT, poll_s: float = POLL_S,
                 clock: Callable[[], datetime] = _utcnow,
                 new_id: Callable[[], str] = lambda: "t_" + secrets.token_hex(6)) -> None:
        self._approvals, self._chat, self._access = approvals, chat, access
        self._timeout, self._poll_s, self._clock, self._new_id = timeout, poll_s, clock, new_id

    # ---- ToolApprovals (tools module) ----

    async def request(self, req: ApprovalRequest) -> ApprovalOutcome:
        now = self._clock()
        try:
            approval = Approval(self._new_id(), req.run_id, req.chat_id, req.tool, req.kind, req.server, req.command,
                                req.reason, ApprovalStatus.PENDING, now, now + self._timeout)
        except InvalidApproval as e:
            return ApprovalOutcome(False, f"refused: {e}", None)

        if req.kind == "read" and await asyncio.to_thread(self._approvals.has_read_grant, req.chat_id, req.server):
            allowed = approval.auto_allowed()
            await asyncio.to_thread(self._approvals.add, allowed)
            await self._show(allowed, "running")
            return ApprovalOutcome(True, allowed.note or "", allowed.id)

        await asyncio.to_thread(self._approvals.add, approval)
        try:
            await self._show(approval, "waiting", chat_status="waiting")
        except ChatNotFound:  # e.g. a fixed dev token: there is no chat to ask in
            await asyncio.to_thread(self._approvals.save, approval.expired())
            return ApprovalOutcome(False, "no chat to ask in", None)

        while True:
            current = await asyncio.to_thread(self._approvals.get, approval.id) or approval
            if not current.pending:
                return ApprovalOutcome(current.status is ApprovalStatus.ALLOWED, current.note or "", current.id)
            if self._clock() >= current.expires_at:
                expired = current.expired()
                await asyncio.to_thread(self._approvals.save, expired)
                await self._show(expired, "denied", chat_status="working")
                return ApprovalOutcome(False, expired.note or "", expired.id)
            await asyncio.sleep(self._poll_s)

    def report(self, call_id: str, status: str, output: str) -> None:
        approval = self._approvals.get(call_id)
        if approval is None or approval.status is not ApprovalStatus.ALLOWED:
            return
        self._chat.publish(approval.chat_id, card(approval, "done" if status == "done" else "failed", output))

    # ---- AnswerApprovals (web app) ----

    def answer(self, user_id: str, chat_id: str, call_id: str, answer: str) -> None:
        approval = self._approvals.get(call_id)
        if approval is None or approval.chat_id != chat_id:
            raise ApprovalNotFound(call_id)
        if not approval.pending:
            raise ApprovalAlreadyDecided(f"this call was already {approval.status.value}")
        if not self._access.can_approve_tool(user_id, approval.kind):
            who = "a developer, devops or admin" if approval.kind == "read" else "devops or an admin"
            raise ApprovalNotAllowed(f"{approval.kind} tools must be approved by {who}")
        try:
            choice = Answer(answer)
        except ValueError as e:
            raise ApprovalNotFound(f"unknown answer {answer!r}") from e
        decided = approval.decided(choice, user_id, self._access.name_of(user_id) or user_id)
        self._approvals.save(decided)
        if decided.grants_reads_for_chat(choice):
            self._approvals.add_read_grant(chat_id, approval.server, user_id)
        self._chat.publish(chat_id, card(decided, "running" if decided.status is ApprovalStatus.ALLOWED else "denied"))
        self._chat.publish(chat_id, {"type": "status", "status": "working"})

    async def _show(self, approval: Approval, status: str, chat_status: str | None = None) -> None:
        await asyncio.to_thread(self._chat.publish, approval.chat_id, card(approval, status))
        if chat_status:
            await asyncio.to_thread(self._chat.publish, approval.chat_id, {"type": "status", "status": chat_status})
