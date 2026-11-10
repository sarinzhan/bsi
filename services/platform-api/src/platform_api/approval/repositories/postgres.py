"""Approvals and "allow reads for this chat" grants in Postgres, with SQLAlchemy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Engine, Index, Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.approval.models import Approval, ApprovalStatus
from platform_api.approval.interfaces import ApprovalRepository
from platform_api.db import Base


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'allowed', 'denied', 'expired')", name="status_known"),
        CheckConstraint("kind IN ('read', 'write', 'full')", name="kind_known"),
        Index(None, "chat_id", "requested_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text)
    chat_id: Mapped[str] = mapped_column(Text)  # no foreign key: chat owns chats
    tool: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    server: Mapped[str] = mapped_column(Text)
    command: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class ReadGrantRow(Base):
    __tablename__ = "approval_read_grants"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    server: Mapped[str] = mapped_column(Text, primary_key=True)
    granted_by: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _to_approval(r: ApprovalRow) -> Approval:
    return Approval(r.id, r.run_id, r.chat_id, r.tool, r.kind, r.server, r.command, r.reason,
                    ApprovalStatus(r.status), r.requested_at, r.expires_at, r.decided_by, r.note)


def _to_row(a: Approval) -> ApprovalRow:
    return ApprovalRow(id=a.id, run_id=a.run_id, chat_id=a.chat_id, tool=a.tool, kind=a.kind, server=a.server,
                       command=a.command, reason=a.reason, status=a.status.value, requested_at=a.requested_at,
                       expires_at=a.expires_at, decided_by=a.decided_by, note=a.note)


class PostgresApprovalRepository(ApprovalRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, approval: Approval) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(_to_row(approval))

    def save(self, approval: Approval) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(_to_row(approval))

    def get(self, approval_id: str) -> Approval | None:
        with Session(self._engine) as session:
            row = session.get(ApprovalRow, approval_id)
            return _to_approval(row) if row else None

    def has_read_grant(self, chat_id: str, server: str) -> bool:
        with Session(self._engine) as session:
            return session.scalar(select(ReadGrantRow.chat_id).where(
                ReadGrantRow.chat_id == chat_id, ReadGrantRow.server == server)) is not None

    def add_read_grant(self, chat_id: str, server: str, user_id: str) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(insert(ReadGrantRow).values(chat_id=chat_id, server=server, granted_by=user_id)
                            .on_conflict_do_nothing())
