"""Inbound adapter: servers HTTP API for the web app (FastAPI).

  GET /api/servers
  PUT /api/servers/{name}/allowed-tools     {"tools": ["docker_ps", ...], "reason": "..."}
  GET /api/servers/{name}/access-history

Who may change access is decided by platform-api (permission servers.manage: devops and admins).
It calls this service with X-Service-Token and passes the user's name in X-User. Without a valid token: 401.
This file only translates HTTP <-> use case calls; the rules live in application/settings.py.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from server_tools.servers.ports.provided import (
    AccessChange, AccessChangeRejected, ServerCatalog, ServerInfo, ServerNotFound, ServerSettings,
)


class ChangeAccessBody(BaseModel):
    tools: list[str]
    reason: str = ""


def servers_router(catalog: ServerCatalog, settings: ServerSettings, service_token: str | None) -> APIRouter:
    router = APIRouter(prefix="/api/servers", tags=["servers"])

    def trusted(x_service_token: str = Header(default="")) -> None:
        if service_token is not None and not hmac.compare_digest(x_service_token, service_token):
            raise HTTPException(401, "unauthorized")  # service_token None = dev mode only

    @router.get("")
    def list_servers() -> list[ServerInfo]:
        return catalog.list()

    @router.put("/{name}/allowed-tools", dependencies=[Depends(trusted)])
    def change_access(name: str, body: ChangeAccessBody, x_user: str = Header(default="developer")) -> ServerInfo:
        try:
            return settings.change_allowed_tools(name, body.tools, x_user, body.reason)
        except ServerNotFound:
            raise HTTPException(404, "server not found") from None
        except AccessChangeRejected as e:
            raise HTTPException(422, str(e)) from None

    @router.get("/{name}/access-history")
    def access_history(name: str) -> list[AccessChange]:
        return settings.access_history(name)

    return router
