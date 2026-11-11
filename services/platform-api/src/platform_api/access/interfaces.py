"""What the access module needs from the outside world."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from platform_api.access.models import Credential, RolesChanged, SessionRecord, User


class UserRepository(Protocol):
    def all(self) -> list[User]: ...

    def save(self, user: User) -> None: ...


class RoleChangeLog(Protocol):
    def append(self, event: RolesChanged) -> None: ...

    def for_user(self, user_id: str) -> list[RolesChanged]: ...


class CredentialStore(Protocol):
    def get(self, user_id: str) -> Credential | None: ...

    def save(self, credential: Credential) -> None: ...


class SessionStore(Protocol):
    def add(self, session: SessionRecord) -> None: ...

    def get(self, token_hash: str) -> SessionRecord | None: ...

    def delete(self, token_hash: str) -> None: ...

    def delete_for_user(self, user_id: str) -> None: ...  # password changed or reset: sign out everywhere

    def delete_expired(self, now: datetime) -> None: ...
