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


class AccessCheck(Protocol):
    """Used by every other module (approval, agent, servers proxy...)."""

    def can(self, user_id: str, permission: str) -> bool: ...

    def can_approve_tool(self, user_id: str, tool_kind: str) -> bool: ...

    def name_of(self, user_id: str) -> str | None: ...  # display name, e.g. on approval cards

    def who_can(self, permission: str) -> list[UserView]: ...  # e.g. "ask a devops": who to notify


class UserAdmin(Protocol):
    """Used by the Users page."""

    def sign_in(self, user_id: str) -> UserView: ...  # unknown user: created without roles

    def me(self, user_id: str) -> UserView: ...

    def list_users(self) -> list[UserView]: ...

    def set_roles(self, actor_id: str, user_id: str, roles: list[str], reason: str) -> UserView: ...

    def role_history(self, user_id: str) -> list[RoleChange]: ...

    def matrix(self) -> dict[str, list[str]]: ...  # role -> permissions, for the UI
