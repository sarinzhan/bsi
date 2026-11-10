"""Router: chats over HTTP (FastAPI). Two callers, two routers.

web app (signed-in user), JSON in the web app's shapes (web/src/api/types.ts):
  GET  /api/chats?systemId=superapp           -> ChatSummary[]
  POST /api/chats {"systemId", "env"?}         -> Chat
  GET  /api/chats/{id}                         -> Chat (+ lastSeq)
  POST /api/chats/{id}/messages {"text"}       -> {"messageId", "afterSeq", "runStatus"}   409 while the agent works
  GET  /api/chats/{id}/events?after=N          -> text/event-stream of AgentEvent (id: seq). follow=false: no waiting

agent container (Authorization: Bearer <run token>; the token tells which chat):
  GET  /runner/context                         -> {"chatId", "system", "env", "messages": [{role, text}]}
  POST /runner/events  {AgentEvent}            -> its own text messages and steps only
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from platform_api.agent.schemas import RunTokens
from platform_api.chat.schemas import (
    ChatBusy, ChatNotAllowed, ChatNotFound, ChatRejected, Chats, ChatSummaryView, ChatView, RunnerChat,
)

POLL_S = 0.5
KEEPALIVE_EVERY = 30  # polls (15 s)


class CreateChatBody(BaseModel):
    system_id: str = Field(alias="systemId")
    env: str = "dev"


class SendBody(BaseModel):
    text: str


def _summary(c: ChatSummaryView) -> dict[str, Any]:
    return {"id": c.id, "systemId": c.system, "env": c.env, "title": c.title, "status": c.status, "projectIds": []}


def _chat(c: ChatView) -> dict[str, Any]:
    return {**_summary(c), "messages": c.messages, "lastSeq": c.last_seq}


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ChatNotAllowed as e:
        raise HTTPException(403, str(e)) from None
    except ChatNotFound:
        raise HTTPException(404, "chat not found") from None
    except ChatBusy as e:
        raise HTTPException(409, str(e)) from None
    except ChatRejected as e:
        raise HTTPException(422, str(e)) from None


def chats_router(chats: Chats, current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api/chats", tags=["chats"])

    def signed_in(request: Request) -> str:
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        return uid

    @router.get("")
    def list_chats(systemId: str, uid: str = Depends(signed_in)) -> list[dict[str, Any]]:  # noqa: N803
        return [_summary(c) for c in _errors(lambda: chats.list(uid, systemId))]

    @router.post("", status_code=201)
    def create(body: CreateChatBody, uid: str = Depends(signed_in)) -> dict[str, Any]:
        return _chat(_errors(lambda: chats.create(uid, body.system_id, body.env)))

    @router.get("/{chat_id}")
    def get(chat_id: str, uid: str = Depends(signed_in)) -> dict[str, Any]:
        return _chat(_errors(lambda: chats.get(uid, chat_id)))

    @router.post("/{chat_id}/messages", status_code=202)
    def send(chat_id: str, body: SendBody, uid: str = Depends(signed_in)) -> dict[str, Any]:
        sent = _errors(lambda: chats.send(uid, chat_id, body.text))
        return {"messageId": sent.message_id, "afterSeq": sent.after_seq, "runStatus": sent.run_status}

    @router.get("/{chat_id}/events")
    async def events(chat_id: str, request: Request, after: int = 0, follow: bool = True,
                     uid: str = Depends(signed_in)) -> StreamingResponse:
        first = _errors(lambda: chats.events_after(uid, chat_id, after))  # checks access before streaming

        async def stream():
            last, idle, batch = after, 0, first
            while True:
                for e in batch:
                    last = e.seq
                    yield f"id: {e.seq}\ndata: {json.dumps(e.body, ensure_ascii=False)}\n\n"
                if not follow or await request.is_disconnected():
                    return
                idle = 0 if batch else idle + 1
                if idle and idle % KEEPALIVE_EVERY == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(POLL_S)
                batch = await asyncio.to_thread(chats.events_after, uid, chat_id, last)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router


def runner_chat_router(chats: RunnerChat, tokens: RunTokens) -> APIRouter:
    router = APIRouter(prefix="/runner", tags=["agent container"])

    def run_chat(authorization: str = Header(default="")) -> str:
        run = tokens.resolve(authorization.removeprefix("Bearer ").strip())
        if run is None:
            raise HTTPException(401, "unknown, ended or expired run token")
        return run.chat_id

    @router.get("/context")
    def context(chat_id: str = Depends(run_chat)) -> dict[str, Any]:
        c = _errors(lambda: chats.context(chat_id))
        return {"chatId": c.chat_id, "system": c.system, "env": c.env, "messages": c.messages}

    @router.post("/events")
    def event(body: dict[str, Any], chat_id: str = Depends(run_chat)) -> dict[str, int]:
        return {"seq": _errors(lambda: chats.runner_event(chat_id, body))}

    return router
