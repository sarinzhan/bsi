"""Roles and permissions. The one place that says who may do what.

- developer: talks to the agent, changes code, lets the agent READ servers (logs, files, state).
- devops:    deploys services and resources (DBs, brokers), approves every change on servers,
             manages servers and the tools the agent may use on them.
- admin:     everything developer and devops can do, plus users and roles, and skills.

A user may have several roles (e.g. developer + devops). Permissions are the union.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    DEVELOPER = "developer"
    DEVOPS = "devops"
    ADMIN = "admin"


class Permission(str, Enum):
    USE_CHAT = "chat.use"  # open chats, ask the agent, see code and history
    CHANGE_CODE = "code.change"  # the agent may commit and open merge requests for you
    APPROVE_SERVER_READ = "server.read.approve"  # folder_list, file_read, docker_ps/logs/inspect/stats
    APPROVE_SERVER_WRITE = "server.write.approve"  # file_write, docker_run, compose_run, compose_restart
    APPROVE_ANY_COMMAND = "server.any_command.approve"  # ssh_exec
    APPROVE_DEPLOY = "deploy.approve"  # deploy services, create/change resources (DBs, brokers)
    MANAGE_SERVERS = "servers.manage"  # add servers, change their allowed tools
    MANAGE_SKILLS = "skills.manage"  # edit the skills the agent follows
    MANAGE_USERS = "users.manage"  # give and take roles


_DEVELOPER = frozenset({
    Permission.USE_CHAT, Permission.CHANGE_CODE, Permission.APPROVE_SERVER_READ,
})
_DEVOPS = frozenset({
    Permission.USE_CHAT, Permission.APPROVE_SERVER_READ, Permission.APPROVE_SERVER_WRITE,
    Permission.APPROVE_ANY_COMMAND, Permission.APPROVE_DEPLOY, Permission.MANAGE_SERVERS,
})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.DEVELOPER: _DEVELOPER,
    Role.DEVOPS: _DEVOPS,
    Role.ADMIN: _DEVELOPER | _DEVOPS | {Permission.MANAGE_SKILLS, Permission.MANAGE_USERS},
}

# Which permission approves which server tool kind (kinds come from the tools module).
APPROVAL_FOR_TOOL_KIND: dict[str, Permission] = {
    "read": Permission.APPROVE_SERVER_READ,
    "write": Permission.APPROVE_SERVER_WRITE,
    "full": Permission.APPROVE_ANY_COMMAND,
}

_ID = re.compile(r"^[a-z][a-z0-9._-]{1,40}$")


class InvalidUser(ValueError):
    pass


@dataclass(frozen=True)
class User:
    """No roles = signed in, but may do nothing until an admin gives a role."""

    id: str
    name: str
    roles: frozenset[Role]

    def __post_init__(self) -> None:
        if not _ID.match(self.id):
            raise InvalidUser(f"bad user id {self.id!r}")

    @property
    def permissions(self) -> frozenset[Permission]:
        return frozenset().union(*(ROLE_PERMISSIONS[r] for r in self.roles))

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles

    def with_roles(self, roles: frozenset[Role]) -> "User":
        return replace(self, roles=frozenset(roles))


@dataclass(frozen=True)
class Credential:
    """A user's password (scrypt hash). must_change: set by an admin (new user, reset) or for the default
    admin; until it is changed the user can only change it (and sign out)."""

    user_id: str
    password_hash: str
    must_change: bool


@dataclass(frozen=True)
class SessionRecord:
    """A signed-in browser. Only the SHA-256 of the cookie's token is stored."""

    token_hash: str
    user_id: str
    expires_at: datetime


@dataclass(frozen=True)
class RolesChanged:
    """Domain event: shown on the Users page, kept forever."""

    user: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    by: str
    reason: str
    at: str
