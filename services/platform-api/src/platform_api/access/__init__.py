"""access module: users, roles (developer, devops, admin) and what each may do."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platform_api.access.adapters.files import JsonlRoleChangeLog, YamlUserRepository
from platform_api.access.application.access import AccessService
from platform_api.access.ports.provided import AccessCheck, UserAdmin


@dataclass(frozen=True)
class AccessModule:
    check: AccessCheck  # for other modules: can(user, permission)
    admin: UserAdmin  # for the Users page


def create_access_module(users_file: Path, role_log: Path) -> AccessModule:
    service = AccessService(YamlUserRepository(users_file), JsonlRoleChangeLog(role_log))
    return AccessModule(check=service, admin=service)
