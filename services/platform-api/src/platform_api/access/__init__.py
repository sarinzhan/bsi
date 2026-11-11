"""access module: users, roles (developer, devops, admin), what each may do, and sign-in with a password."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Iterable

from platform_api.access.auth import AuthService
from platform_api.access.interfaces import CredentialStore, RoleChangeLog, SessionStore, UserRepository
from platform_api.access.models import User
from platform_api.access.repositories.memory import (
    InMemoryCredentialStore, InMemoryRoleChangeLog, InMemorySessionStore, InMemoryUserRepository,
)
from platform_api.access.schemas import AccessCheck, Auth, UserAdmin
from platform_api.access.service import AccessService

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class AccessModule:
    check: AccessCheck  # for other modules: can(user, permission)
    admin: UserAdmin  # for the Users page
    auth: Auth  # sign-in, sessions, passwords


def create_access_module(engine: "Engine | None" = None, users: Iterable[User] = (),
                         default_admin: tuple[str, str] | None = None,
                         session_ttl: timedelta = timedelta(hours=12),
                         jwt_secret: str | None = None) -> AccessModule:
    """engine: everything in Postgres (the platform). No engine: in memory, for tests (`users`).

    default_admin: (user name, password) created as an admin on first start, if that user has no password
    yet (BSI_ADMIN_USERNAME / BSI_ADMIN_PASSWORD). The password must be changed at the first sign-in.
    Other users are added by an admin on the Users page.
    jwt_secret: signs the sign-in tokens (BSI_JWT_SECRET). None: a random one (tests; tokens end on restart).
    """
    repo: UserRepository
    log: RoleChangeLog
    credentials: CredentialStore
    sessions: SessionStore
    if engine is None:
        repo, log = InMemoryUserRepository(users), InMemoryRoleChangeLog()
        credentials, sessions = InMemoryCredentialStore(), InMemorySessionStore()
    else:
        from platform_api.access.repositories.postgres import (
            PostgresCredentialStore, PostgresRoleChangeLog, PostgresSessionStore, PostgresUserRepository,
        )

        repo, log = PostgresUserRepository(engine), PostgresRoleChangeLog(engine)
        credentials, sessions = PostgresCredentialStore(engine), PostgresSessionStore(engine)
    service = AccessService(repo, log)
    auth = AuthService(service, credentials, sessions, jwt_secret or secrets.token_urlsafe(48), session_ttl)
    if default_admin:
        auth.ensure_default_admin(*default_admin)
    return AccessModule(check=service, admin=service, auth=auth)
