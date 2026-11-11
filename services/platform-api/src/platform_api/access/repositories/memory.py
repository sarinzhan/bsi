"""Users and role changes in memory. For tests only: the platform itself always uses Postgres."""

from __future__ import annotations

from typing import Iterable

from platform_api.access.interfaces import RoleChangeLog, UserRepository
from platform_api.access.models import RolesChanged, User


class InMemoryUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users = {u.id: u for u in users}

    def all(self) -> list[User]:
        return list(self._users.values())

    def save(self, user: User) -> None:
        self._users[user.id] = user


class InMemoryRoleChangeLog(RoleChangeLog):
    def __init__(self) -> None:
        self._events: list[RolesChanged] = []

    def append(self, event: RolesChanged) -> None:
        self._events.append(event)

    def for_user(self, user_id: str) -> list[RolesChanged]:
        return [e for e in self._events if e.user == user_id]
