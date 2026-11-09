"""access module: users, roles (developer, devops, admin) and what each may do."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from platform_api.access.adapters.files import JsonlRoleChangeLog, YamlUserRepository
from platform_api.access.application.access import AccessService
from platform_api.access.domain.roles import RolesChanged
from platform_api.access.ports.provided import AccessCheck, UserAdmin
from platform_api.access.ports.required import RoleChangeLog, UserRepository

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class AccessModule:
    check: AccessCheck  # for other modules: can(user, permission)
    admin: UserAdmin  # for the Users page


def create_access_module(users_file: Path, role_log: Path, pool: "ConnectionPool | None" = None) -> AccessModule:
    """pool given: users and role changes live in Postgres; users_file seeds an empty database.
    No pool: users.yaml is the store and role changes go to a JSONL file (tests, quick local runs).
    """
    users: UserRepository
    log: RoleChangeLog
    if pool is None:
        users, log = YamlUserRepository(users_file), JsonlRoleChangeLog(role_log)
    else:
        from platform_api.access.adapters.postgres import PostgresRoleChangeLog, PostgresUserRepository

        users, log = PostgresUserRepository(pool), PostgresRoleChangeLog(pool)
        if users.is_empty() and users_file.exists():
            _seed(users, log, YamlUserRepository(users_file), users_file.name)
    service = AccessService(users, log)
    return AccessModule(check=service, admin=service)


def _seed(target: UserRepository, log: RoleChangeLog, source: UserRepository, file: str) -> None:
    """First start on an empty database: import the YAML file, and log it like any other role change."""
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for user in source.all():
        target.save(user)
        log.append(RolesChanged(user.id, tuple(sorted(r.value for r in user.roles)), (), "system",
                                f"imported from {file}", at))
