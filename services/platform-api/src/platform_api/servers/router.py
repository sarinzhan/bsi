"""Router: servers over HTTP (FastAPI), for the web app (signed-in user):

  GET /api/servers
  PUT /api/servers/{name}/allowed-tools     {"tools": ["docker_ps", ...], "reason": "..."}   devops/admin
  GET /api/servers/{name}/access-history


This file only translates HTTP <-> service calls; the rules (who may change access, which tools exist,
no ssh_exec on prod) live in application/settings.py and the domain.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from platform_api.servers.schemas import (
    AccessChange, AccessChangeNotAllowed, AccessChangeRejected, ServerCatalog, ServerInfo, ServerNotFound,
    ServerSettings,
)


class ChangeAccessBody(BaseModel):
    tools: list[str]
    reason: str = ""


def servers_router(catalog: ServerCatalog, settings: ServerSettings,
                   current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api/servers", tags=["servers"])

    def signed_in(request: Request) -> str:
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        return uid

    @router.get("", dependencies=[Depends(signed_in)])
    def list_servers() -> list[ServerInfo]:
        return catalog.list()

    @router.put("/{name}/allowed-tools")
    def change_access(name: str, body: ChangeAccessBody, uid: str = Depends(signed_in)) -> ServerInfo:
        try:
            return settings.change_allowed_tools(name, body.tools, uid, body.reason)
        except AccessChangeNotAllowed as e:
            raise HTTPException(403, str(e)) from None
        except ServerNotFound:
            raise HTTPException(404, "server not found") from None
        except AccessChangeRejected as e:
            raise HTTPException(422, str(e)) from None

    @router.get("/tools", dependencies=[Depends(signed_in)])  # before /{name}/...: a fixed path wins
    def tools() -> list[dict[str, str]]:
        """The tools that exist (the tools module's catalog). Web app: GET /api/servers/tools."""
        return catalog.tools()

    @router.get("/{name}/access-history", dependencies=[Depends(signed_in)])
    def access_history(name: str) -> list[AccessChange]:
        return settings.access_history(name)

    return router
