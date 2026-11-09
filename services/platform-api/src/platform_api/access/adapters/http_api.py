"""Inbound adapter: access HTTP API for the web app.

  GET /api/me                        current user, roles, permissions
  GET /api/users                     all users (any signed-in user)
  PUT /api/users/{id}/roles          {"roles": [...], "reason": "..."}   admins only
  GET /api/users/{id}/role-history
  GET /api/roles                     role -> permissions (the matrix shown in the UI)

Who is calling: `current_user(request)` (passed in). In dev it reads X-User-Id; in prod it will
read the SSO session. Nothing here decides permissions: the use cases do.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from platform_api.access.ports.provided import NotAllowed, RoleChangeRejected, UserAdmin, UserNotFound


def access_routes(admin: UserAdmin, current_user: Callable[[Request], str | None]) -> list[Route]:
    def signed_in(request: Request) -> str | JSONResponse:
        uid = current_user(request)
        if not uid:
            return JSONResponse({"error": "not signed in"}, status_code=401)
        try:
            admin.me(uid)
        except UserNotFound:
            return JSONResponse({"error": "unknown user"}, status_code=401)
        return uid

    async def me(request: Request) -> JSONResponse:
        uid = signed_in(request)
        return uid if isinstance(uid, JSONResponse) else JSONResponse(asdict(admin.me(uid)))

    async def users(request: Request) -> JSONResponse:
        uid = signed_in(request)
        return uid if isinstance(uid, JSONResponse) else JSONResponse([asdict(u) for u in admin.list_users()])

    async def set_roles(request: Request) -> JSONResponse:
        uid = signed_in(request)
        if isinstance(uid, JSONResponse):
            return uid
        body = await request.json()
        roles = body.get("roles")
        if not isinstance(roles, list):
            return JSONResponse({"error": "roles must be a list"}, status_code=422)
        try:
            view = admin.set_roles(uid, request.path_params["id"], [str(r) for r in roles], str(body.get("reason", "")))
        except NotAllowed as e:
            return JSONResponse({"error": str(e)}, status_code=403)
        except UserNotFound:
            return JSONResponse({"error": "user not found"}, status_code=404)
        except RoleChangeRejected as e:
            return JSONResponse({"error": str(e)}, status_code=422)
        return JSONResponse(asdict(view))

    async def history(request: Request) -> JSONResponse:
        uid = signed_in(request)
        if isinstance(uid, JSONResponse):
            return uid
        return JSONResponse([asdict(c) for c in admin.role_history(request.path_params["id"])])

    async def roles(_: Request) -> JSONResponse:
        return JSONResponse(admin.matrix())

    return [
        Route("/api/me", me),
        Route("/api/users", users),
        Route("/api/users/{id}/roles", set_roles, methods=["PUT"]),
        Route("/api/users/{id}/role-history", history),
        Route("/api/roles", roles),
    ]
