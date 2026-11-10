"""Agent runs in Postgres, with SQLAlchemy. Stores the token's hash, never the token."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Engine, Index, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.agent.models import ACTIVE, Run, RunStatus
from platform_api.agent.interfaces import RunRepository
from platform_api.db import Base

_STATUSES = ", ".join(f"'{s.value}'" for s in RunStatus)


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status_known"),
        CheckConstraint("env IN ('dev', 'stage', 'prod')", name="env_known"),
        CheckConstraint("expires_at > created_at", name="expires_after_start"),
        Index(None, "token_hash", unique=True),
        Index(None, "status", "expires_at"),  # the reaper's query
        Index(None, "chat_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text)
    system: Mapped[str] = mapped_column(Text)
    env: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(Text)  # no foreign key: access owns users
    token_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


def _to_run(r: RunRow) -> Run:
    return Run(r.id, r.chat_id, r.system, r.env, r.requested_by, r.token_hash, RunStatus(r.status),
               r.created_at, r.expires_at, r.error)


def _to_row(run: Run) -> RunRow:
    return RunRow(id=run.id, chat_id=run.chat_id, system=run.system, env=run.env, requested_by=run.requested_by,
                  token_hash=run.token_hash, status=run.status.value, created_at=run.created_at,
                  expires_at=run.expires_at, error=run.error)


class PostgresRunRepository(RunRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, run: Run) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(_to_row(run))

    def save(self, run: Run) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(_to_row(run))

    def get(self, run_id: str) -> Run | None:
        with Session(self._engine) as session:
            row = session.get(RunRow, run_id)
            return _to_run(row) if row else None

    def by_token_hash(self, token_hash: str) -> Run | None:
        with Session(self._engine) as session:
            row = session.scalar(select(RunRow).where(RunRow.token_hash == token_hash))
            return _to_run(row) if row else None

    def active_overdue(self, now: datetime) -> list[Run]:
        with Session(self._engine) as session:
            rows = session.scalars(select(RunRow).where(RunRow.status.in_([s.value for s in ACTIVE]),
                                                        RunRow.expires_at <= now))
            return [_to_run(r) for r in rows]
