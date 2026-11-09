"""Inbound adapter: agent runs over HTTP (FastAPI). Three callers, three routers:

web app (signed-in user):
  POST /api/runs                   {"chatId", "system", "env"} -> run (201). Until the chat module exists,
                                   this is how a run is started by hand.
  GET  /api/runs/{run_id}
  POST /api/runs/{run_id}/cancel

server-tools (X-Service-Token):
  POST /internal/runs/resolve      {"token"} -> {"runId","chatId","system","env","requestedBy"} | 404
                                   (the token goes in the body, never in the URL: URLs end up in access logs)

agent container (Authorization: Bearer <run token>):
  POST /runner/finish              {"outcome": "finished" | "failed", "error"?}
"""

from __future__ import annotations

import hmac
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from platform_api.agent.ports.provided import RunInfo, RunNotAllowed, RunNotFound, RunRejected, Runs, RunTokens


class StartRunBody(BaseModel):
    chat_id: str = Field(alias="chatId")
    system: str
    env: str


class ResolveBody(BaseModel):
    token: str


class FinishBody(BaseModel):
    outcome: Literal["finished", "failed"]
    error: str | None = Field(default=None, max_length=2000)


class RunContextOut(BaseModel):
    """The contract server-tools reads (PlatformRunAuthority). Do not rename fields."""

    runId: str
    chatId: str
    system: str
    env: str
    requestedBy: str


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


def internal_router(tokens: RunTokens, service_token: str | None) -> APIRouter:
    router = APIRouter(prefix="/internal", tags=["internal"])

    def trusted(x_service_token: str = Header(default="")) -> None:
        if service_token is not None and not hmac.compare_digest(x_service_token, service_token):
            raise HTTPException(401, "unauthorized")  # service_token None = dev mode only

    @router.post("/runs/resolve", dependencies=[Depends(trusted)])
    def resolve(body: ResolveBody) -> RunContextOut:
        run = tokens.resolve(body.token)
        if run is None:
            raise HTTPException(404, "unknown, ended or expired run token")
        return RunContextOut(runId=run.run_id, chatId=run.chat_id, system=run.system, env=run.env,
                             requestedBy=run.requested_by)

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
