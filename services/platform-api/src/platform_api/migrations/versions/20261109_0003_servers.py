"""servers, access_changes (servers module, moved here from agent-tools)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "servers",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("systems", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("allowed_tools", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("ssh_user", sa.Text(), server_default="deploy", nullable=False),
        sa.Column("ssh_port", sa.Integer(), server_default="22", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("name ~ '^[a-z0-9][a-z0-9-]{1,62}$'", name=op.f("ck_servers_name_format")),
        sa.CheckConstraint("env IN ('dev', 'stage', 'prod')", name=op.f("ck_servers_env_known")),
        sa.CheckConstraint("ssh_port BETWEEN 1 AND 65535", name=op.f("ck_servers_ssh_port_range")),
        sa.CheckConstraint("NOT (env = 'prod' AND 'ssh_exec' = ANY (allowed_tools))",
                           name=op.f("ck_servers_no_ssh_exec_on_prod")),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_servers")),
    )
    op.create_table(
        "access_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("server", sa.Text(), nullable=False),
        sa.Column("added", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("removed", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["server"], ["servers.name"], name=op.f("fk_access_changes_server_servers")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_changes")),
    )
    op.create_index(op.f("ix_access_changes_server_id"), "access_changes", ["server", "id"])
    # append-only history; forbid_change() was created in 0001
    op.execute("CREATE TRIGGER access_changes_append_only BEFORE UPDATE OR DELETE ON access_changes "
               "FOR EACH ROW EXECUTE FUNCTION forbid_change()")
    op.execute("CREATE TRIGGER access_changes_no_truncate BEFORE TRUNCATE ON access_changes "
               "FOR EACH STATEMENT EXECUTE FUNCTION forbid_change()")


def downgrade() -> None:
    op.drop_table("access_changes")
    op.drop_table("servers")
