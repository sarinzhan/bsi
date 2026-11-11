"""Users, role changes, passwords and sessions in Postgres, with SQLAlchemy.

The ORM models (UserRow, RoleChangeRow) are a storage detail of this repository. The rest of the module
only sees the domain classes (User, RolesChanged): the repositories convert between the two.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Engine, ForeignKey, Identity, Index, Text, delete, func, select,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform_api.access.models import Credential, Role, RolesChanged, SessionRecord, User
from platform_api.access.interfaces import CredentialStore, RoleChangeLog, SessionStore, UserRepository
from platform_api.db import Base


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("id ~ '^[a-z][a-z0-9._-]{1,40}$'", name="id_format"),
        # only known roles; none = signed in, waiting for an admin to give a role
        CheckConstraint("roles <@ ARRAY['developer', 'devops', 'admin']", name="roles_valid"),
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


class CredentialRow(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    must_change: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)  # SHA-256 of the JWT
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class PostgresCredentialStore(CredentialStore):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, user_id: str) -> Credential | None:
        with Session(self._engine) as session:
            row = session.get(CredentialRow, user_id)
            return Credential(row.user_id, row.password_hash, row.must_change) if row else None

    def save(self, credential: Credential) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(CredentialRow(user_id=credential.user_id, password_hash=credential.password_hash,
                                        must_change=credential.must_change))


class PostgresSessionStore(SessionStore):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, record: SessionRecord) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(SessionRow(token_hash=record.token_hash, user_id=record.user_id,
                                   expires_at=record.expires_at))

    def get(self, token_hash: str) -> SessionRecord | None:
        with Session(self._engine) as session:
            row = session.get(SessionRow, token_hash)
            return SessionRecord(row.token_hash, row.user_id, row.expires_at) if row else None

    def _delete(self, *where) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(delete(SessionRow).where(*where))

    def delete(self, token_hash: str) -> None:
        self._delete(SessionRow.token_hash == token_hash)

    def delete_for_user(self, user_id: str) -> None:
        self._delete(SessionRow.user_id == user_id)

    def delete_expired(self, now: datetime) -> None:
        self._delete(SessionRow.expires_at <= now)
