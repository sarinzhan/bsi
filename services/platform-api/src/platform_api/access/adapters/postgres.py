"""Outbound adapter: users and role changes in Postgres, with SQLAlchemy.

The ORM models (UserRow, RoleChangeRow) are a storage detail of this adapter. The rest of the module
only sees the domain classes (User, RolesChanged): the repositories convert between the two.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Engine, ForeignKey, Identity, Index, Text, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.access.domain.roles import Role, RolesChanged, User
from platform_api.access.ports.required import RoleChangeLog, UserRepository
from platform_api.db import Base


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("id ~ '^[a-z][a-z0-9._-]{1,40}$'", name="id_format"),
        # every user keeps at least one role, and only known roles
        CheckConstraint("cardinality(roles) >= 1 AND roles <@ ARRAY['developer', 'devops', 'admin']",
                        name="roles_valid"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class RoleChangeRow(Base):
    """Append-only (a trigger rejects UPDATE, DELETE and TRUNCATE, see the migration)."""

    __tablename__ = "role_changes"
    __table_args__ = (Index(None, "user_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"))
    added: Mapped[list[str]] = mapped_column(ARRAY(Text))
    removed: Mapped[list[str]] = mapped_column(ARRAY(Text))
    by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresUserRepository(UserRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def all(self) -> list[User]:
        with Session(self._engine) as session:
            return [User(r.id, r.name, frozenset(Role(x) for x in r.roles))
                    for r in session.scalars(select(UserRow).order_by(UserRow.id))]

    def save(self, user: User) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(UserRow(id=user.id, name=user.name, roles=sorted(r.value for r in user.roles)))

    def is_empty(self) -> bool:
        with Session(self._engine) as session:
            return session.scalar(select(UserRow.id).limit(1)) is None


class PostgresRoleChangeLog(RoleChangeLog):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, event: RolesChanged) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(RoleChangeRow(user_id=event.user, added=list(event.added), removed=list(event.removed),
                                      by=event.by, reason=event.reason, at=datetime.fromisoformat(event.at)))

    def for_user(self, user_id: str) -> list[RolesChanged]:
        """Oldest first, like the JSONL log."""
        with Session(self._engine) as session:
            rows = session.scalars(select(RoleChangeRow).where(RoleChangeRow.user_id == user_id)
                                   .order_by(RoleChangeRow.id))
            return [RolesChanged(r.user_id, tuple(r.added), tuple(r.removed), r.by, r.reason,
                                 r.at.astimezone(timezone.utc).isoformat(timespec="seconds"))
                    for r in rows]
