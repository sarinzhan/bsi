"""init: servers, access_changes (servers module), audit_log (tools module)

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

APPEND_ONLY = ("access_changes", "audit_log")  # history is never edited or deleted


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
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("server", sa.Text(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('rejected', 'denied', 'failed', 'done')", name=op.f("ck_audit_log_status_known")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_chat_id_id"), "audit_log", ["chat_id", "id"])
    op.create_index(op.f("ix_audit_log_at"), "audit_log", ["at"])

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
    op.drop_table("audit_log")
    op.drop_table("access_changes")
    op.drop_table("servers")
    op.execute("DROP FUNCTION forbid_change()")
