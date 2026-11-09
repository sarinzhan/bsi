"""Users and role changes in Postgres (the platform database)."""

from __future__ import annotations

from datetime import timezone

from psycopg_pool import ConnectionPool

from platform_api.access.domain.roles import Role, RolesChanged, User
from platform_api.access.ports.required import RoleChangeLog, UserRepository


class PostgresUserRepository(UserRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def all(self) -> list[User]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT id, name, roles FROM users ORDER BY id").fetchall()
        return [User(r[0], r[1], frozenset(Role(x) for x in r[2])) for r in rows]

    def save(self, user: User) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO users (id, name, roles) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, roles = EXCLUDED.roles, updated_at = now()",
                (user.id, user.name, sorted(r.value for r in user.roles)),
            )

    def is_empty(self) -> bool:
        with self._pool.connection() as conn:
            return conn.execute("SELECT NOT EXISTS (SELECT 1 FROM users)").fetchone()[0]


class PostgresRoleChangeLog(RoleChangeLog):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, event: RolesChanged) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO role_changes (user_id, added, removed, by, reason, at) "
                "VALUES (%s, %s, %s, %s, %s, %s::timestamptz)",
                (event.user, list(event.added), list(event.removed), event.by, event.reason, event.at),
            )

    def for_user(self, user_id: str) -> list[RolesChanged]:
        """Oldest first, like the JSONL log."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT user_id, added, removed, by, reason, at FROM role_changes WHERE user_id = %s ORDER BY id",
                (user_id,),
            ).fetchall()
        return [
            RolesChanged(r[0], tuple(r[1]), tuple(r[2]), r[3], r[4],
                         r[5].astimezone(timezone.utc).isoformat(timespec="seconds"))
            for r in rows
        ]
