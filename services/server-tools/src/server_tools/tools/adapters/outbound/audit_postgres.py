"""Outbound adapter: audit log in Postgres, with SQLAlchemy. One row per tool call. Append-only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Engine, Identity, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from server_tools.db import Base
from server_tools.tools.ports.required import AuditLog, AuditRecord


class AuditRow(Base):
    """Append-only (a trigger rejects UPDATE, DELETE and TRUNCATE, see the migration)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("status IN ('rejected', 'denied', 'failed', 'done')", name="status_known"),
        Index(None, "chat_id", "id"),
        Index(None, "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    run_id: Mapped[str] = mapped_column(Text)
    chat_id: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text)
    server: Mapped[str] = mapped_column(Text)  # no foreign key: the tools module does not own servers
    command: Mapped[str] = mapped_column(Text)  # masked, exactly as shown on the approval card
    approved_by: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)


class PostgresAuditLog(AuditLog):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, record: AuditRecord) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(AuditRow(
                run_id=record.run_id, chat_id=record.chat_id, requested_by=record.requested_by, tool=record.tool,
                server=record.server, command=record.command, approved_by=record.approved_by,
                status=record.status, exit_code=record.exit_code,
            ))
