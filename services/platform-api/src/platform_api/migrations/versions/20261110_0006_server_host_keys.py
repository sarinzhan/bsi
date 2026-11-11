"""Servers added from the web app: pinned SSH host key and the last connection check.
Users may have no roles (signed in, waiting for an admin).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('servers', sa.Column('host_key', sa.Text(), nullable=True))
    op.add_column('servers', sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('servers', sa.Column('docker_version', sa.Text(), nullable=True))
    op.add_column('servers', sa.Column('memory_total_bytes', sa.BigInteger(), nullable=True))
    op.add_column('servers', sa.Column('memory_used_bytes', sa.BigInteger(), nullable=True))
    op.add_column('servers', sa.Column('check_error', sa.Text(), nullable=True))
    op.drop_constraint(op.f('ck_users_roles_valid'), 'users', type_='check')
    op.create_check_constraint(op.f('ck_users_roles_valid'), 'users',
                               "roles <@ ARRAY['developer', 'devops', 'admin']")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_users_roles_valid'), 'users', type_='check')
    op.create_check_constraint(op.f('ck_users_roles_valid'), 'users',
                               "cardinality(roles) >= 1 AND roles <@ ARRAY['developer', 'devops', 'admin']")
    for column in ('check_error', 'memory_used_bytes', 'memory_total_bytes', 'docker_version', 'checked_at',
                   'host_key'):
        op.drop_column('servers', column)
