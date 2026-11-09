"""Postgres plumbing for the composition root: the connection pool and the schema migrations.

Migrations are plain SQL files in `migrations/` (NNNN_title.sql), applied in order, each in one
transaction, and recorded in `schema_migrations`. Never edit an applied file: add a new one.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

MIGRATIONS = Path(__file__).with_name("migrations")
_LOCK = 7_420_001  # pg_advisory_lock key: two replicas starting at once do not migrate twice


def migrate(conninfo: str, directory: Path = MIGRATIONS) -> list[str]:
    """Applies the SQL files that are not applied yet. Returns their names."""
    applied: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            for file in sorted(directory.glob("*.sql")):
                if file.stem in done:
                    continue
                with conn.transaction():
                    conn.execute(file.read_text())
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (file.stem,))
                applied.append(file.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK,))
    return applied


def open_pool(conninfo: str) -> ConnectionPool:
    """Adapters convert timestamps to UTC themselves, so the session time zone does not matter."""
    pool = ConnectionPool(conninfo, min_size=1, max_size=10, open=False)
    pool.open(wait=True, timeout=10)  # fail at startup, not on the first tool call
    return pool
