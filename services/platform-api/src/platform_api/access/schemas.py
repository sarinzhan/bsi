"""What the access module offers. Other modules ask `can(user, permission)`; they never look at roles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UserView:
    id: str
    name: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True)
class RoleChange:
    user: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    by: str
    reason: str
    at: str


class UserNotFound(LookupError):
    pass


class NotAllowed(PermissionError):
    """The actor lacks the permission. Message says which one."""


class RoleChangeRejected(ValueError):
    pass


class UserRejected(ValueError):
    """A new user can not be created (bad id, already exists). Message says why."""


class LoginFailed(PermissionError):
    """Wrong user name or password. Never says which of the two."""


class TooManyAttempts(PermissionError):
    """Too many wrong passwords for this user name: try again in a minute."""


@dataclass(frozen=True)
class SignedIn:
    """Who a session cookie belongs to. must_change_password: the only thing they may do is change it."""

    user_id: str
    must_change_password: bool


class AccessCheck(Protocol):
    """Used by every other module (approval, agent, servers proxy...)."""

    def can(self, user_id: str, permission: str) -> bool: ...

    def can_approve_tool(self, user_id: str, tool_kind: str) -> bool: ...

    def name_of(self, user_id: str) -> str | None: ...  # display name, e.g. on approval cards

    def who_can(self, permission: str) -> list[UserView]: ...  # e.g. "ask a devops": who to notify


class UserAdmin(Protocol):
    """Used by the Users page."""

    def me(self, user_id: str) -> UserView: ...

    def list_users(self) -> list[UserView]: ...

    def add_user(self, actor_id: str, user_id: str, name: str, roles: list[str]) -> UserView: ...  # admins

    def set_roles(self, actor_id: str, user_id: str, roles: list[str], reason: str) -> UserView: ...

    def role_history(self, user_id: str) -> list[RoleChange]: ...

    def matrix(self) -> dict[str, list[str]]: ...  # role -> permissions, for the UI


class Auth(Protocol):
    """Sign-in with a user name and password; the browser keeps a session cookie (the token)."""

    def login(self, user_id: str, password: str) -> tuple[str, SignedIn]: ...  # (token, who)

    def session(self, token: str) -> SignedIn | None: ...  # None: unknown, expired or signed out

    def logout(self, token: str) -> None: ...

    def change_password(self, user_id: str, current: str, new: str) -> str: ...  # a new token

    def create_user(self, actor_id: str, user_id: str, name: str, roles: list[str], password: str) -> UserView: ...

    def reset_password(self, actor_id: str, user_id: str, password: str) -> None: ...  # admins
