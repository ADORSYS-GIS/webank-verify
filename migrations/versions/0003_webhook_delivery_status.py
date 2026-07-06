"""add webhook_delivery_status to verifications

Tracks whether the post-approval/rejection webhook was successfully
delivered to the BFF. Enables the reconciliation job and the dashboard
warning banner.

Values:
  pending   — webhook not yet fired (or in-flight, or record pre-dates this column)
  delivered — BFF confirmed receipt with 2xx
  failed    — all retry attempts exhausted

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verifications",
        sa.Column(
            "webhook_delivery_status",
            sa.String,
            nullable=False,
            server_default="pending",
        ),
    )
    # Index for the reconciliation query: find approved/rejected with failed webhooks
    op.create_index(
        "ix_verifications_webhook_delivery_status",
        "verifications",
        ["webhook_delivery_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_verifications_webhook_delivery_status", table_name="verifications")
    op.drop_column("verifications", "webhook_delivery_status")
