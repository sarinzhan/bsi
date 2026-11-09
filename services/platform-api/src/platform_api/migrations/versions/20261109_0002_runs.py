"""runs: agent runs (agent module). Stores the run token's hash, never the token.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('starting', 'running', 'finished', 'failed', 'cancelled', 'expired')",
                           name=op.f("ck_runs_status_known")),
        sa.CheckConstraint("env IN ('dev', 'stage', 'prod')", name=op.f("ck_runs_env_known")),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_runs_expires_after_start")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_index(op.f("ix_runs_token_hash"), "runs", ["token_hash"], unique=True)
    op.create_index(op.f("ix_runs_status_expires_at"), "runs", ["status", "expires_at"])
    op.create_index(op.f("ix_runs_chat_id_created_at"), "runs", ["chat_id", "created_at"])


def downgrade() -> None:
    op.drop_table("runs")
