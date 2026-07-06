"""add fraud_flag to verifications

Persists the fraud flag at reject time so the reconciliation job and the
resend endpoint can rebuild the webhook payload without losing it
(fail-closed on fraud — see review feedback on PR #63).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verifications",
        sa.Column(
            "fraud_flag",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("verifications", "fraud_flag")