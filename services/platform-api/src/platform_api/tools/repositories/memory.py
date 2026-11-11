"""Audit log in memory. For tests only: the platform itself always uses Postgres."""

from __future__ import annotations

from platform_api.tools.interfaces import AuditLog, AuditRecord


class InMemoryAuditLog(AuditLog):
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def write(self, record: AuditRecord) -> None:
        self.records.append(record)
