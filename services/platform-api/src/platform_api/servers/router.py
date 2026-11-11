"""Router: servers over HTTP (FastAPI), for the web app (signed-in user):

  GET  /api/systems                              systems some server serves, with their envs
  GET  /api/servers
  GET  /api/servers/tools                        the tools that exist
  GET  /api/servers/ssh-public-key               the platform's key, for authorized_keys      devops/admin
  POST /api/servers/host-key  {"host", "port"}   the server's SSH host key + fingerprint     devops/admin
  POST /api/servers  {"name", "host", "env", "systems", "ssh_user", "ssh_port", "host_key"}   devops/admin
  POST /api/servers/{name}/check                 SSH in, read Docker version and memory      devops/admin
  PUT  /api/servers/{name}/allowed-tools  {"tools": [...], "reason": "..."}                   devops/admin
  GET  /api/servers/{name}/access-history

Only translates HTTP <-> service calls; the rules live in service.py and models.py.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from platform_api.servers.schemas import (
    AccessChange, AccessChangeNotAllowed, AccessChangeRejected, HostKey, HostUnreachable, NewServer, ServerAdmin,
    ServerCatalog, ServerInfo, ServerNotFound, ServerRejected, ServerSettings, SystemInfo,
)


class ChangeAccessBody(BaseModel):
    tools: list[str]
    reason: str = ""


class HostKeyBody(BaseModel):
    host: str
    port: int = Field(22, ge=1, le=65535)


class AddServerBody(BaseModel):
    name: str
    host: str
    env: str
    systems: list[str]
    ssh_user: str = "deploy"
    ssh_port: int = Field(22, ge=1, le=65535)
    host_key: str


def _errors(e: Exception) -> HTTPException:
    if isinstance(e, AccessChangeNotAllowed):
        return HTTPException(403, str(e))
    if isinstance(e, ServerNotFound):
        return HTTPException(404, "server not found")
    if isinstance(e, (AccessChangeRejected, ServerRejected)):
        return HTTPException(422, str(e))
    if isinstance(e, HostUnreachable):
        return HTTPException(502, str(e))
    raise e


def servers_router(catalog: ServerCatalog, settings: ServerSettings, admin: ServerAdmin,
                   current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["servers"])
    known = (AccessChangeNotAllowed, ServerNotFound, AccessChangeRejected, ServerRejected, HostUnreachable)

    def signed_in(request: Request) -> str:
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        return uid

    @router.get("/systems", dependencies=[Depends(signed_in)])
    def systems() -> list[SystemInfo]:
        return catalog.systems()

    @router.get("/servers", dependencies=[Depends(signed_in)])
    def list_servers() -> list[ServerInfo]:
        return catalog.list()

    # fixed paths before /servers/{name}/...
    @router.get("/servers/tools", dependencies=[Depends(signed_in)])
    def tools() -> list[dict[str, str]]:
        return catalog.tools()

    @router.get("/servers/ssh-public-key")
    def public_key(uid: str = Depends(signed_in)) -> dict[str, str]:
        try:
            return {"public_key": admin.platform_public_key(uid)}
        except known as e:
            raise _errors(e) from None

    @router.post("/servers/host-key")
    async def host_key(body: HostKeyBody, uid: str = Depends(signed_in)) -> HostKey:
        try:
            return await admin.fetch_host_key(body.host.strip(), body.port, uid)
        except known as e:
            raise _errors(e) from None

    @router.post("/servers", status_code=201)
    def add(body: AddServerBody, uid: str = Depends(signed_in)) -> ServerInfo:
        try:
            return admin.add(NewServer(body.name, body.host, body.env, tuple(body.systems), body.ssh_user,
                                       body.ssh_port, body.host_key), uid)
        except known as e:
            raise _errors(e) from None

    @router.post("/servers/{name}/check")
    async def check(name: str, uid: str = Depends(signed_in)) -> ServerInfo:
        try:
            return await admin.check(name, uid)
        except known as e:
            raise _errors(e) from None

    @router.put("/servers/{name}/allowed-tools")
    def change_access(name: str, body: ChangeAccessBody, uid: str = Depends(signed_in)) -> ServerInfo:
        try:
            return settings.change_allowed_tools(name, body.tools, uid, body.reason)
        except known as e:
            raise _errors(e) from None

    @router.get("/servers/{name}/access-history", dependencies=[Depends(signed_in)])
    def access_history(name: str) -> list[AccessChange]:
        return settings.access_history(name)

    return router
