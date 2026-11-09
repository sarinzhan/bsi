"""Servers and access changes in Postgres (the server_tools database)."""

from __future__ import annotations

from datetime import timezone

from psycopg_pool import ConnectionPool

from server_tools.servers.domain.server import AccessChanged, Env, Server
from server_tools.servers.ports.required import AccessChangeLog, ServerRepository

_COLUMNS = "name, host, env, systems, allowed_tools, ssh_user, ssh_port"


class PostgresServerRepository(ServerRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def all(self) -> list[Server]:
        with self._pool.connection() as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM servers ORDER BY name").fetchall()
        return [
            Server(name=r[0], host=r[1], env=Env(r[2]), systems=frozenset(r[3]), allowed_tools=frozenset(r[4]),
                   ssh_user=r[5], ssh_port=r[6])
            for r in rows
        ]

    def save(self, server: Server) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                f"INSERT INTO servers ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (name) DO UPDATE SET host = EXCLUDED.host, env = EXCLUDED.env, "
                "systems = EXCLUDED.systems, allowed_tools = EXCLUDED.allowed_tools, "
                "ssh_user = EXCLUDED.ssh_user, ssh_port = EXCLUDED.ssh_port, updated_at = now()",
                (server.name, server.host, server.env.value, sorted(server.systems), sorted(server.allowed_tools),
                 server.ssh_user, server.ssh_port),
            )

    def is_empty(self) -> bool:
        with self._pool.connection() as conn:
            return conn.execute("SELECT NOT EXISTS (SELECT 1 FROM servers)").fetchone()[0]


class PostgresAccessChangeLog(AccessChangeLog):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append(self, event: AccessChanged) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO access_changes (server, added, removed, by, reason, at) "
                "VALUES (%s, %s, %s, %s, %s, %s::timestamptz)",
                (event.server, list(event.added), list(event.removed), event.by, event.reason, event.at),
            )

    def for_server(self, name: str) -> list[AccessChanged]:
        """Oldest first, like the JSONL log."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT server, added, removed, by, reason, at FROM access_changes WHERE server = %s ORDER BY id",
                (name,),
            ).fetchall()
        return [
            AccessChanged(r[0], tuple(r[1]), tuple(r[2]), r[3], r[4],
                          r[5].astimezone(timezone.utc).isoformat(timespec="seconds"))
            for r in rows
        ]
