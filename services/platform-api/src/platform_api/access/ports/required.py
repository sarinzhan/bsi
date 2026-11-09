"""What the access module needs from the outside world."""

from __future__ import annotations

from typing import Protocol

from platform_api.access.domain.roles import RolesChanged, User


class UserRepository(Protocol):
    def all(self) -> list[User]: ...

    def save(self, user: User) -> None: ...


class RoleChangeLog(Protocol):
    def append(self, event: RolesChanged) -> None: ...

    def for_user(self, user_id: str) -> list[RolesChanged]: ...
