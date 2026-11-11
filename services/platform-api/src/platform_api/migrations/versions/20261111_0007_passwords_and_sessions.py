"""Sign-in with a password: password hashes and browser sessions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_credentials',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('must_change', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_credentials_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_user_credentials')),
    )
    op.create_table(
        'sessions',
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash', name=op.f('pk_sessions')),
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('user_credentials')
