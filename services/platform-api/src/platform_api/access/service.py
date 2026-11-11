"""Access service: permission checks and role administration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from platform_api.access.models import (
    APPROVAL_FOR_TOOL_KIND, ROLE_PERMISSIONS, InvalidUser, Permission, Role, RolesChanged, User,
)
from platform_api.access.schemas import (
    AccessCheck, NotAllowed, RoleChange, RoleChangeRejected, UserAdmin, UserNotFound, UserRejected, UserView,
)
from platform_api.access.interfaces import RoleChangeLog, UserRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _view(u: User) -> UserView:
    return UserView(u.id, u.name, tuple(sorted(r.value for r in u.roles)),
                    tuple(sorted(p.value for p in u.permissions)))


class AccessService(AccessCheck, UserAdmin):
    def __init__(self, users: UserRepository, log: RoleChangeLog) -> None:
        self._users, self._log = users, log

    def _find(self, user_id: str) -> User:
        user = next((u for u in self._users.all() if u.id == user_id), None)
        if user is None:
            raise UserNotFound(user_id)
        return user

    # ---- AccessCheck ----

    def name_of(self, user_id: str) -> str | None:
        try:
            return self._find(user_id).name
        except UserNotFound:
            return None


    def can(self, user_id: str, permission: str) -> bool:
        try:
            return self._find(user_id).can(Permission(permission))
        except (UserNotFound, ValueError):
            return False  # unknown user or permission: deny, never guess

    def can_approve_tool(self, user_id: str, tool_kind: str) -> bool:
        permission = APPROVAL_FOR_TOOL_KIND.get(tool_kind)
        return permission is not None and self.can(user_id, permission.value)

    def who_can(self, permission: str) -> list[UserView]:
        p = Permission(permission)
        return [_view(u) for u in self._users.all() if u.can(p)]

    # ---- UserAdmin ----

    def add_user(self, actor_id: str, user_id: str, name: str, roles: list[str]) -> UserView:
        actor = self._find(actor_id)
        if not actor.can(Permission.MANAGE_USERS):
            raise NotAllowed("only admins can add users")
        return self._create(user_id, name, roles, actor.name, "new user")

    def ensure_user(self, user_id: str, roles: Iterable[Role], reason: str) -> bool:
        """Bootstrap (the default admin): creates the user if missing. Existing users are left alone, so
        taking someone's admin role away is not undone on restart. True if created."""
        if any(u.id == user_id for u in self._users.all()):
            return False
        self._create(user_id, user_id, [r.value for r in roles], "system", reason)
        return True

    def _create(self, user_id: str, name: str, roles: list[str], by: str, reason: str) -> UserView:
        user_id = user_id.strip().lower()
        if any(u.id == user_id for u in self._users.all()):
            raise UserRejected(f"user {user_id!r} already exists")
        try:
            user = User(user_id, name.strip() or user_id, frozenset(Role(r) for r in roles))
        except InvalidUser:
            raise UserRejected("user name: 2-41 characters, lowercase letters, digits, . _ -, starting with a "
                               "letter") from None
        except ValueError:
            raise UserRejected(f"unknown role in {roles}") from None
        self._users.save(user)
        self._log.append(RolesChanged(user_id, tuple(sorted(r.value for r in user.roles)), (), by, reason, _now()))
        return _view(user)

    def me(self, user_id: str) -> UserView:
        return _view(self._find(user_id))

    def list_users(self) -> list[UserView]:
        return [_view(u) for u in sorted(self._users.all(), key=lambda u: u.name)]

    def set_roles(self, actor_id: str, user_id: str, roles: list[str], reason: str) -> UserView:
        actor = self._find(actor_id)
        if not actor.can(Permission.MANAGE_USERS):
            raise NotAllowed("only admins can change roles")
        user = self._find(user_id)
        reason = (reason or "").strip()
        if not reason or len(reason) > 200:
            raise RoleChangeRejected("say why you change the roles (one line, up to 200 characters)")
        try:
            wanted = frozenset(Role(r) for r in roles)
            changed = user.with_roles(wanted)
        except ValueError as e:  # unknown role or InvalidUser (no roles)
            raise RoleChangeRejected(str(e) if isinstance(e, InvalidUser) else f"unknown role in {roles}") from e
        if user.is_admin and not changed.is_admin and sum(u.is_admin for u in self._users.all()) == 1:
            raise RoleChangeRejected("this is the last admin; make someone else admin first")
        if changed == user:
            return _view(user)
        self._users.save(changed)
        self._log.append(RolesChanged(
            user_id, tuple(sorted(r.value for r in wanted - user.roles)),
            tuple(sorted(r.value for r in user.roles - wanted)),
            actor.name, reason, _now(),
        ))
        return _view(changed)

    def role_history(self, user_id: str) -> list[RoleChange]:
        return [RoleChange(e.user, e.added, e.removed, e.by, e.reason, e.at)
                for e in reversed(self._log.for_user(user_id))]

    def matrix(self) -> dict[str, list[str]]:
        return {r.value: sorted(p.value for p in ps) for r, ps in ROLE_PERMISSIONS.items()}
