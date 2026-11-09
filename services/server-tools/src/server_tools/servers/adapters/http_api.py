"""Inbound adapter: servers HTTP API for the web app.

  GET /api/servers
  PUT /api/servers/{name}/allowed-tools     {"tools": ["docker_ps", ...], "reason": "..."}
  GET /api/servers/{name}/access-history

Who may change access is decided by platform-api (permission servers.manage: devops and admins).
It calls this service with X-Service-Token and passes the user's name in X-User. Without a valid token: 401.
"""

from __future__ import annotations

import hmac
from dataclasses import asdict

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server_tools.servers.ports.provided import AccessChangeRejected, ServerCatalog, ServerNotFound, ServerSettings


def server_routes(catalog: ServerCatalog, settings: ServerSettings, service_token: str | None) -> list[Route]:
    def trusted(request: Request) -> bool:
        if service_token is None:  # dev mode only
            return True
        return hmac.compare_digest(request.headers.get("x-service-token", ""), service_token)

    async def list_servers(_: Request) -> JSONResponse:
        return JSONResponse([asdict(s) for s in catalog.list()])

    async def change_access(request: Request) -> JSONResponse:
        if not trusted(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        try:
            tools = body.get("tools")
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                return JSONResponse({"error": "tools must be a list of tool names"}, status_code=422)
            info = settings.change_allowed_tools(request.path_params["name"], tools,
                                                 request.headers.get("x-user", "developer"), str(body.get("reason", "")))
        except ServerNotFound:
            return JSONResponse({"error": "server not found"}, status_code=404)
        except AccessChangeRejected as e:
            return JSONResponse({"error": str(e)}, status_code=422)
        return JSONResponse(asdict(info))

    async def history(request: Request) -> JSONResponse:
        return JSONResponse([asdict(c) for c in settings.access_history(request.path_params["name"])])

    return [
        Route("/api/servers", list_servers),
        Route("/api/servers/{name}/allowed-tools", change_access, methods=["PUT"]),
        Route("/api/servers/{name}/access-history", history),
    ]
