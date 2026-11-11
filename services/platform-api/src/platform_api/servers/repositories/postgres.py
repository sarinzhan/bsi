"""Servers and access changes in Postgres, with SQLAlchemy.

The ORM models (ServerRow, AccessChangeRow) are a storage detail of this repository. The rest of the module
only sees the domain classes (Server, AccessChanged): the repositories convert between the two.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Engine, ForeignKey, Identity, Index, Integer, Text, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.db import Base
from platform_api.servers.models import AccessChanged, Env, Health, Server
from platform_api.servers.interfaces import AccessChangeLog, ServerRepository


class ServerRow(Base):
    __tablename__ = "servers"
    __table_args__ = (
        CheckConstraint("name ~ '^[a-z0-9][a-z0-9-]{1,62}$'", name="name_format"),
        CheckConstraint("env IN ('dev', 'stage', 'prod')", name="env_known"),
        CheckConstraint("ssh_port BETWEEN 1 AND 65535", name="ssh_port_range"),
        # the same rule as the domain, so a hand-written UPDATE cannot break it either
        CheckConstraint("NOT (env = 'prod' AND 'ssh_exec' = ANY (allowed_tools))", name="no_ssh_exec_on_prod"),
    )

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    host: Mapped[str] = mapped_column(Text)
    env: Mapped[str] = mapped_column(Text)
    systems: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")  # systems allowed here
    allowed_tools: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")  # empty = nothing
    ssh_user: Mapped[str] = mapped_column(Text, server_default="deploy")
    ssh_port: Mapped[int] = mapped_column(Integer, server_default="22")
    host_key: Mapped[str | None] = mapped_column(Text)  # pinned SSH host key; NULL = SSH refused
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last connection check
    docker_version: Mapped[str | None] = mapped_column(Text)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger)
    check_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class AccessChangeRow(Base):
    """Append-only (a trigger rejects UPDATE, DELETE and TRUNCATE, see the migration)."""

    __tablename__ = "access_changes"
    __table_args__ = (Index(None, "server", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    server: Mapped[str] = mapped_column(Text, ForeignKey("servers.name"))
    added: Mapped[list[str]] = mapped_column(ARRAY(Text))
    removed: Mapped[list[str]] = mapped_column(ARRAY(Text))
    by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _to_server(row: ServerRow) -> Server:
    health = None
    if row.checked_at is not None:
        health = Health(_iso(row.checked_at), row.docker_version, row.memory_total_bytes, row.memory_used_bytes,
                        row.check_error)
    return Server(name=row.name, host=row.host, env=Env(row.env), systems=frozenset(row.systems),
                  allowed_tools=frozenset(row.allowed_tools), ssh_user=row.ssh_user, ssh_port=row.ssh_port,
                  host_key=row.host_key, health=health)


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat(timespec="seconds")


class PostgresServerRepository(ServerRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def all(self) -> list[Server]:
        with Session(self._engine) as session:
            return [_to_server(r) for r in session.scalars(select(ServerRow).order_by(ServerRow.name))]

    def save(self, server: Server) -> None:
        with Session(self._engine) as session, session.begin():
            h = server.health
            session.merge(ServerRow(
                name=server.name, host=server.host, env=server.env.value, systems=sorted(server.systems),
                allowed_tools=sorted(server.allowed_tools), ssh_user=server.ssh_user, ssh_port=server.ssh_port,
                host_key=server.host_key,
                checked_at=datetime.fromisoformat(h.checked_at) if h else None,
                docker_version=h.docker_version if h else None,
                memory_total_bytes=h.memory_total_bytes if h else None,
                memory_used_bytes=h.memory_used_bytes if h else None,
                check_error=h.error if h else None,
            ))


class PostgresAccessChangeLog(AccessChangeLog):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, event: AccessChanged) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(AccessChangeRow(server=event.server, added=list(event.added), removed=list(event.removed),
                                        by=event.by, reason=event.reason, at=datetime.fromisoformat(event.at)))

    def for_server(self, name: str) -> list[AccessChanged]:
        """Oldest first, like the JSONL log."""
        with Session(self._engine) as session:
            rows = session.scalars(select(AccessChangeRow).where(AccessChangeRow.server == name)
                                   .order_by(AccessChangeRow.id))
            return [AccessChanged(r.server, tuple(r.added), tuple(r.removed), r.by, r.reason, _iso(r.at))
                    for r in rows]
