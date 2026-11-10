"""Router: agent runs over HTTP (FastAPI). Two callers, two routers:

web app (signed-in user):
  POST /api/runs                   {"chatId", "system", "env"} -> run (201). Until the chat module exists,
                                   this is how a run is started by hand.
  GET  /api/runs/{run_id}
  POST /api/runs/{run_id}/cancel

agent container (Authorization: Bearer <run token>):
  POST /runner/finish              {"outcome": "finished" | "failed", "error"?}
"""

from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from platform_api.agent.schemas import RunInfo, RunNotAllowed, RunNotFound, RunRejected, Runs, RunTokens


class StartRunBody(BaseModel):
    chat_id: str = Field(alias="chatId")
    system: str
    env: str


class FinishBody(BaseModel):
    outcome: Literal["finished", "failed"]
    error: str | None = Field(default=None, max_length=2000)


def runs_router(runs: Runs, current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api/runs", tags=["agent runs"])

    def signed_in(request: Request) -> str:
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        return uid

    @router.post("", status_code=201)
    def start(body: StartRunBody, uid: str = Depends(signed_in)) -> RunInfo:
        try:
            return runs.start(uid, body.chat_id, body.system, body.env)
        except RunNotAllowed as e:
            raise HTTPException(403, str(e)) from None
        except RunRejected as e:
            raise HTTPException(422, str(e)) from None

    @router.get("/{run_id}", dependencies=[Depends(signed_in)])
    def get(run_id: str) -> RunInfo:
        try:
            return runs.get(run_id)
        except RunNotFound:
            raise HTTPException(404, "run not found") from None

    @router.post("/{run_id}/cancel")
    def cancel(run_id: str, uid: str = Depends(signed_in)) -> RunInfo:
        try:
            return runs.cancel(uid, run_id)
        except RunNotFound:
            raise HTTPException(404, "run not found") from None
        except RunNotAllowed as e:
            raise HTTPException(403, str(e)) from None

    return router


def runner_router(tokens: RunTokens) -> APIRouter:
    router = APIRouter(prefix="/runner", tags=["agent container"])

    def run_token(authorization: str = Header(default="")) -> str:
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "missing run token")
        return token

    @router.post("/finish")
    def finish(body: FinishBody, token: str = Depends(run_token)) -> RunInfo:
        try:
            return tokens.finish(token, body.outcome, body.error)
        except RunNotFound:
            raise HTTPException(401, "unknown, ended or expired run token") from None

    return router
