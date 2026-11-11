"""Users, role changes, passwords and sessions in memory. For tests only: the platform always uses Postgres."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from platform_api.access.interfaces import CredentialStore, RoleChangeLog, SessionStore, UserRepository
from platform_api.access.models import Credential, RolesChanged, SessionRecord, User


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


class InMemoryCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self._items: dict[str, Credential] = {}

    def get(self, user_id: str) -> Credential | None:
        return self._items.get(user_id)

    def save(self, credential: Credential) -> None:
        self._items[credential.user_id] = credential


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._items: dict[str, SessionRecord] = {}

    def add(self, session: SessionRecord) -> None:
        self._items[session.token_hash] = session

    def get(self, token_hash: str) -> SessionRecord | None:
        return self._items.get(token_hash)

    def delete(self, token_hash: str) -> None:
        self._items.pop(token_hash, None)

    def delete_for_user(self, user_id: str) -> None:
        self._items = {k: s for k, s in self._items.items() if s.user_id != user_id}

    def delete_expired(self, now: datetime) -> None:
        self._items = {k: s for k, s in self._items.items() if s.expires_at > now}
