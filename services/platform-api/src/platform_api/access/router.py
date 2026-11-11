"""Router: access HTTP API for the web app (FastAPI).

  POST /api/auth/login               {"username", "password"} -> {"token": JWT, "user"}
  POST /api/auth/logout              ends this token's session (Authorization: Bearer <token>)
  GET  /api/me                       current user, roles, permissions, must_change_password
  POST /api/me/password              {"current", "new"} -> {"token", "user"}: a new token; all old ones end
  GET  /api/users                    all users (any signed-in user)
  POST /api/users                    {"id", "name", "roles", "password"}   admins only; a temporary password
  PUT  /api/users/{id}/roles         {"roles": [...], "reason": "..."}   admins only
  PUT  /api/users/{id}/password      {"password"}   admins only; the user must change it at the next sign-in
  GET  /api/users/{id}/role-history
  GET  /api/roles                    role -> permissions (the matrix shown in the UI)

Who is calling: `current_user(request)` (passed in; main.py reads the Bearer token). It gives no one while
the user still has to change their password: then only /me, /me/password and logout work. Nothing here
decides permissions: the services do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from platform_api.access.passwords import PasswordRejected
from platform_api.access.schemas import (
    Auth, LoginFailed, NotAllowed, RoleChange, RoleChangeRejected, SignedIn, TooManyAttempts, UserAdmin,
    UserNotFound, UserRejected, UserView,
)


def bearer_token(request: Request) -> str | None:
    """The sign-in token from "Authorization: Bearer <jwt>"."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def signed_in_as(auth: "Auth", request: Request) -> "SignedIn | None":
    token = bearer_token(request)
    return auth.session(token) if token else None


@dataclass(frozen=True)
class MeView:
    id: str
    name: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    must_change_password: bool


@dataclass(frozen=True)
class TokenView:
    """The browser keeps `token` and sends it as "Authorization: Bearer <token>"."""

    token: str
    user: MeView


class SetRolesBody(BaseModel):
    roles: list[str]
    reason: str = ""


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current: str
    new: str


class NewUserBody(BaseModel):
    id: str
    name: str = ""
    roles: list[str] = []
    password: str


class ResetPasswordBody(BaseModel):
    password: str


def access_router(admin: UserAdmin, current_user: Callable[[Request], str | None],
                  auth: Auth | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["access"])

    def signed_in(request: Request) -> str:
        """FastAPI dependency: the id of a known, signed-in user, or 401."""
        uid = current_user(request)
        if not uid:
            raise HTTPException(401, "not signed in")
        try:
            admin.me(uid)
        except UserNotFound:
            raise HTTPException(401, "not signed in") from None
        return uid

    def caller(request: Request) -> tuple[str, bool]:
        """Like signed_in, but also a user who still has to change their password: (id, must_change)."""
        session = signed_in_as(auth, request) if auth is not None else None
        if session is not None:
            return session.user_id, session.must_change_password
        return signed_in(request), False

    def me_view(uid: str, must_change: bool) -> MeView:
        v = admin.me(uid)
        return MeView(v.id, v.name, v.roles, v.permissions, must_change)

    if auth is not None:
        @router.post("/auth/login")
        def login(body: LoginBody) -> TokenView:
            try:
                token, who = auth.login(body.username, body.password)
            except LoginFailed as e:
                raise HTTPException(401, str(e)) from None
            except TooManyAttempts as e:
                raise HTTPException(429, str(e)) from None
            return TokenView(token, me_view(who.user_id, who.must_change_password))

        @router.post("/auth/logout", status_code=204)
        def logout(request: Request) -> None:
            token = bearer_token(request)
            if token:
                auth.logout(token)

        @router.post("/me/password")
        def change_password(body: ChangePasswordBody, who: tuple[str, bool] = Depends(caller)) -> TokenView:
            try:
                token = auth.change_password(who[0], body.current, body.new)
            except PasswordRejected as e:
                raise HTTPException(422, str(e)) from None
            return TokenView(token, me_view(who[0], False))  # the old token no longer works

        @router.post("/users", status_code=201)
        def add_user(body: NewUserBody, uid: str = Depends(signed_in)) -> UserView:
            try:
                return auth.create_user(uid, body.id, body.name, body.roles, body.password)
            except NotAllowed as e:
                raise HTTPException(403, str(e)) from None
            except (UserRejected, PasswordRejected) as e:
                raise HTTPException(422, str(e)) from None

        @router.put("/users/{user_id}/password", status_code=204)
        def reset_password(user_id: str, body: ResetPasswordBody, uid: str = Depends(signed_in)) -> None:
            try:
                auth.reset_password(uid, user_id, body.password)
            except NotAllowed as e:
                raise HTTPException(403, str(e)) from None
            except UserNotFound:
                raise HTTPException(404, "user not found") from None
            except PasswordRejected as e:
                raise HTTPException(422, str(e)) from None

    @router.get("/me")
    def me(who: tuple[str, bool] = Depends(caller)) -> MeView:
        return me_view(*who)

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
