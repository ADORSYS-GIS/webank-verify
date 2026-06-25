"""add person_id to verifications

Stable biometric identity key (ADR 0005). See webank-verify#2.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("verifications", sa.Column("person_id", sa.String, nullable=True))
    op.create_index("ix_verifications_person_id", "verifications", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_verifications_person_id", table_name="verifications")
    op.drop_column("verifications", "person_id")
