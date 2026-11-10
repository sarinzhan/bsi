"""Router: access HTTP API for the web app (FastAPI).

  GET /api/me                        current user, roles, permissions
  GET /api/users                     all users (any signed-in user)
  PUT /api/users/{id}/roles          {"roles": [...], "reason": "..."}   admins only
  GET /api/users/{id}/role-history
  GET /api/roles                     role -> permissions (the matrix shown in the UI)

Who is calling: `current_user(request)` (passed in). In dev it reads X-User-Id; in prod it will
read the SSO session. Nothing here decides permissions: the service does.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from platform_api.access.schemas import (
    NotAllowed, RoleChange, RoleChangeRejected, UserAdmin, UserNotFound, UserView,
)


class SetRolesBody(BaseModel):
    roles: list[str]
    reason: str = ""


def access_router(admin: UserAdmin, current_user: Callable[[Request], str | None]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["access"])

    def signed_in(request: Request) -> str:
        """FastAPI dependency: the id of a known, signed-in user, or 401."""
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        try:
            admin.me(uid)
        except UserNotFound:
            raise HTTPException(401, "unknown user") from None
        return uid

    @router.get("/me")
    def me(uid: str = Depends(signed_in)) -> UserView:
        return admin.me(uid)

    @router.get("/users", dependencies=[Depends(signed_in)])
    def users() -> list[UserView]:
        return admin.list_users()

    @router.put("/users/{user_id}/roles")
    def set_roles(user_id: str, body: SetRolesBody, uid: str = Depends(signed_in)) -> UserView:
        try:
            return admin.set_roles(uid, user_id, body.roles, body.reason)
        except NotAllowed as e:
            raise HTTPException(403, str(e)) from None
        except UserNotFound:
            raise HTTPException(404, "user not found") from None
        except RoleChangeRejected as e:
            raise HTTPException(422, str(e)) from None

    @router.get("/users/{user_id}/role-history", dependencies=[Depends(signed_in)])
    def role_history(user_id: str) -> list[RoleChange]:
        return admin.role_history(user_id)

    @router.get("/roles")
    def roles() -> dict[str, list[str]]:
        return admin.matrix()

    return router
