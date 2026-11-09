"""init: users, role_changes (access module)

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = ("role_changes",)  # history is never edited or deleted


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id ~ '^[a-z][a-z0-9._-]{1,40}$'", name=op.f("ck_users_id_format")),
        sa.CheckConstraint("cardinality(roles) >= 1 AND roles <@ ARRAY['developer', 'devops', 'admin']",
                           name=op.f("ck_users_roles_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "role_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("added", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("removed", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_role_changes_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_changes")),
    )
    op.create_index(op.f("ix_role_changes_user_id_id"), "role_changes", ["user_id", "id"])

    # Append-only history: Alembic does not model triggers, so they are plain SQL.
    op.execute("""
        CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only: rows are never changed or deleted', TG_TABLE_NAME;
        END $$
    """)
    for table in APPEND_ONLY:
        op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION forbid_change()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION forbid_change()")


def downgrade() -> None:
    op.drop_table("role_changes")
    op.drop_table("users")
    op.execute("DROP FUNCTION forbid_change()")
