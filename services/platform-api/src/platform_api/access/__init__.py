"""access module: users, roles (developer, devops, admin) and what each may do."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from platform_api.access.interfaces import RoleChangeLog, UserRepository
from platform_api.access.models import User
from platform_api.access.repositories.memory import InMemoryRoleChangeLog, InMemoryUserRepository
from platform_api.access.schemas import AccessCheck, UserAdmin
from platform_api.access.service import AccessService

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class AccessModule:
    check: AccessCheck  # for other modules: can(user, permission)
    admin: UserAdmin  # for the Users page and sign-in


def create_access_module(engine: "Engine | None" = None, admins: Iterable[str] = (),
                         users: Iterable[User] = ()) -> AccessModule:
    """engine: users and role changes in Postgres (the platform). No engine: in memory, for tests (`users`).

    admins: user ids that become admins if they do not exist yet (BSI_ADMINS): how the first admin gets in.
    Everyone else is created on first sign-in without roles, until an admin gives them one.
    """
    repo: UserRepository
    log: RoleChangeLog
    if engine is None:
        repo, log = InMemoryUserRepository(users), InMemoryRoleChangeLog()
    else:
        from platform_api.access.repositories.postgres import PostgresRoleChangeLog, PostgresUserRepository

        repo, log = PostgresUserRepository(engine), PostgresRoleChangeLog(engine)
    service = AccessService(repo, log)
    service.ensure_admins(admins)
    return AccessModule(check=service, admin=service)
