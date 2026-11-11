"""Router: access HTTP API for the web app (FastAPI).

  POST /api/auth/login               {"username", "password"} -> session cookie + who you are
  POST /api/auth/logout              ends this session
  GET  /api/me                       current user, roles, permissions, must_change_password
  POST /api/me/password              {"current", "new"}: change your own password (signs out other browsers)
  GET  /api/users                    all users (any signed-in user)
  POST /api/users                    {"id", "name", "roles", "password"}   admins only; a temporary password
  PUT  /api/users/{id}/roles         {"roles": [...], "reason": "..."}   admins only
  PUT  /api/users/{id}/password      {"password"}   admins only; the user must change it at the next sign-in
  GET  /api/users/{id}/role-history
  GET  /api/roles                    role -> permissions (the matrix shown in the UI)

Who is calling: `current_user(request)` (passed in; main.py reads the session cookie). It gives no one while
the user still has to change their password: then only /me, /me/password and logout work. Nothing here
decides permissions: the services do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from platform_api.access.passwords import PasswordRejected
from platform_api.access.schemas import (
    Auth, LoginFailed, NotAllowed, RoleChange, RoleChangeRejected, TooManyAttempts, UserAdmin, UserNotFound,
    UserRejected, UserView,
)


@dataclass(frozen=True)
class SessionCookie:
    name: str = "bsi_session"
    path: str = "/"  # the app's base path, e.g. "/bsi/" behind a shared nginx: not sent to the other apps
    secure: bool = False  # True behind HTTPS (the browser then never sends it over plain HTTP)
    max_age_s: int = 12 * 3600

    def set(self, response: Response, token: str) -> None:
        response.set_cookie(self.name, token, max_age=self.max_age_s, path=self.path, secure=self.secure,
                            httponly=True, samesite="strict")

    def clear(self, response: Response) -> None:
        response.delete_cookie(self.name, path=self.path, secure=self.secure, httponly=True, samesite="strict")


@dataclass(frozen=True)
class MeView:
    id: str
    name: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    must_change_password: bool


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


def access_router(admin: UserAdmin, current_user: Callable[[Request], str | None], auth: Auth | None = None,
                  cookie: SessionCookie = SessionCookie()) -> APIRouter:
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
        token = request.cookies.get(cookie.name)
        if auth is not None and token:
            session = auth.session(token)
            if session is not None:
                return session.user_id, session.must_change_password
        return signed_in(request), False

    def me_view(uid: str, must_change: bool) -> MeView:
        v = admin.me(uid)
        return MeView(v.id, v.name, v.roles, v.permissions, must_change)

    if auth is not None:
        @router.post("/auth/login")
        def login(body: LoginBody, response: Response) -> MeView:
            try:
                token, who = auth.login(body.username, body.password)
            except LoginFailed as e:
                raise HTTPException(401, str(e)) from None
            except TooManyAttempts as e:
                raise HTTPException(429, str(e)) from None
            cookie.set(response, token)
            return me_view(who.user_id, who.must_change_password)

        @router.post("/auth/logout", status_code=204)
        def logout(request: Request, response: Response) -> None:
            token = request.cookies.get(cookie.name)
            if token:
                auth.logout(token)
            cookie.clear(response)

        @router.post("/me/password", status_code=204)
        def change_password(body: ChangePasswordBody, response: Response,
                            who: tuple[str, bool] = Depends(caller)) -> None:
            try:
                token = auth.change_password(who[0], body.current, body.new)
            except PasswordRejected as e:
                raise HTTPException(422, str(e)) from None
            cookie.set(response, token)

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
