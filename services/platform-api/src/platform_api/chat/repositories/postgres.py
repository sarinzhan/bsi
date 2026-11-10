"""Chats, messages and events in Postgres, with SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Engine, ForeignKey, Identity, Index, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.chat.models import Chat, ChatMessage, ChatStatus
from platform_api.chat.interfaces import ChatRepository
from platform_api.db import Base


class ChatRow(Base):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("status IN ('working', 'waiting', 'failed')", name="status_known"),
        CheckConstraint("env IN ('dev', 'stage', 'prod')", name="env_known"),
        Index(None, "system", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    system: Mapped[str] = mapped_column(Text)
    env: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text)  # no foreign key: access owns users
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_run_id: Mapped[str | None] = mapped_column(Text)  # no foreign key: agent owns runs


class ChatMessageRow(Base):
    """The current state of each message (upserted by id). `position` keeps the order they first appeared."""

    __tablename__ = "chat_messages"
    __table_args__ = (Index(None, "chat_id", "position"),)

    chat_id: Mapped[str] = mapped_column(Text, ForeignKey("chats.id"), primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(Text)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class ChatEventRow(Base):
    """Append-only (trigger in the migration). The browser streams these after the last seq it saw."""

    __tablename__ = "chat_events"
    __table_args__ = (Index(None, "chat_id", "seq"),)

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, ForeignKey("chats.id"))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _to_chat(r: ChatRow) -> Chat:
    return Chat(r.id, r.system, r.env, r.title, ChatStatus(r.status), r.created_by, r.created_at, r.active_run_id)


def _to_row(c: Chat) -> ChatRow:
    return ChatRow(id=c.id, system=c.system, env=c.env, title=c.title, status=c.status.value,
                   created_by=c.created_by, created_at=c.created_at, active_run_id=c.active_run_id)


class PostgresChatRepository(ChatRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, chat: Chat) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(_to_row(chat))

    def get(self, chat_id: str) -> Chat | None:
        with Session(self._engine) as session:
            row = session.get(ChatRow, chat_id)
            return _to_chat(row) if row else None

    def list(self, system: str) -> list[Chat]:
        with Session(self._engine) as session:
            rows = session.scalars(select(ChatRow).where(ChatRow.system == system).order_by(ChatRow.created_at.desc()))
            return [_to_chat(r) for r in rows]

    def messages(self, chat_id: str) -> list[ChatMessage]:
        with Session(self._engine) as session:
            rows = session.scalars(select(ChatMessageRow).where(ChatMessageRow.chat_id == chat_id)
                                   .order_by(ChatMessageRow.position))
            return [ChatMessage(r.chat_id, r.id, r.role, r.body) for r in rows]

    def record(self, chat_id: str, event: dict[str, Any], message: ChatMessage | None = None,
               chat: Chat | None = None) -> int:
        with Session(self._engine) as session, session.begin():
            row = ChatEventRow(chat_id=chat_id, body=event)
            session.add(row)
            session.flush()  # assigns seq
            if message is not None:
                stmt = insert(ChatMessageRow).values(chat_id=chat_id, id=message.id, position=row.seq,
                                                     role=message.role, body=message.body)
                session.execute(stmt.on_conflict_do_update(  # keep the original position
                    index_elements=["chat_id", "id"], set_={"body": stmt.excluded.body, "updated_at": func.now()}))
            if chat is not None:
                session.merge(_to_row(chat))
            return row.seq

    def events_after(self, chat_id: str, after_seq: int, limit: int) -> list[tuple[int, dict[str, Any]]]:
        with Session(self._engine) as session:
            rows = session.execute(select(ChatEventRow.seq, ChatEventRow.body)
                                   .where(ChatEventRow.chat_id == chat_id, ChatEventRow.seq > after_seq)
                                   .order_by(ChatEventRow.seq).limit(limit))
            return [(seq, body) for seq, body in rows]

    def last_seq(self, chat_id: str) -> int:
        with Session(self._engine) as session:
            return session.scalar(select(func.coalesce(func.max(ChatEventRow.seq), 0))
                                  .where(ChatEventRow.chat_id == chat_id))
