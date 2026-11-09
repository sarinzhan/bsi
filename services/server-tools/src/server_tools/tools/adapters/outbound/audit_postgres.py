"""Audit log in Postgres: one row per tool call (who, what, where, approved by, result). Append-only."""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from server_tools.tools.ports.required import AuditLog, AuditRecord


class PostgresAuditLog(AuditLog):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def write(self, record: AuditRecord) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (run_id, chat_id, requested_by, tool, server, command, approved_by, status,"
                " exit_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (record.run_id, record.chat_id, record.requested_by, record.tool, record.server, record.command,
                 record.approved_by, record.status, record.exit_code),
            )
