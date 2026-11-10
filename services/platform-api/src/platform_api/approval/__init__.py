"""approval module: a person decides whether a server tool call may run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_api.access.schemas import AccessCheck
from platform_api.approval.repositories.memory import InMemoryApprovalRepository
from platform_api.approval.service import ApprovalService
from platform_api.approval.schemas import AnswerApprovals, ToolApprovals
from platform_api.approval.interfaces import ApprovalRepository
from platform_api.chat.schemas import ChatEventSink

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class ApprovalModule:
    tools: ToolApprovals  # the tools module
    answers: AnswerApprovals  # web app


def create_approval_module(chat: ChatEventSink, access: AccessCheck, engine: "Engine | None" = None) -> ApprovalModule:
    repo: ApprovalRepository
    if engine is None:
        repo = InMemoryApprovalRepository()
    else:
        from platform_api.approval.repositories.postgres import PostgresApprovalRepository

        repo = PostgresApprovalRepository(engine)
    service = ApprovalService(repo, chat, access)
    return ApprovalModule(tools=service, answers=service)
