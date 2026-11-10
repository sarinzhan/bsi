"""Router: approvals over HTTP (FastAPI), for the web app (signed-in user):
  POST /api/chats/{chatId}/tool-calls/{callId}/answer  {answer: allow_chat | allow_once | deny}
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from platform_api.approval.schemas import (
    AnswerApprovals, ApprovalAlreadyDecided, ApprovalNotAllowed, ApprovalNotFound,
)


class AnswerBody(BaseModel):
    answer: str


def approvals_router(approvals: AnswerApprovals, current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api/chats", tags=["approvals"])

    def signed_in(request: Request) -> str:
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        return uid

    @router.post("/{chat_id}/tool-calls/{call_id}/answer", status_code=204)
    def answer(chat_id: str, call_id: str, body: AnswerBody, uid: str = Depends(signed_in)) -> None:
        try:
            approvals.answer(uid, chat_id, call_id, body.answer)
        except ApprovalNotAllowed as e:
            raise HTTPException(403, str(e)) from None
        except ApprovalNotFound:
            raise HTTPException(404, "tool call not found") from None
        except ApprovalAlreadyDecided as e:
            raise HTTPException(409, str(e)) from None

    return router
