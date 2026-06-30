"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verifications",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("doc_type", sa.String, nullable=True),
        sa.Column("country", sa.String, server_default="CM"),
        sa.Column("document_fields", JSONB, nullable=True),
        sa.Column("liveness_metrics", JSONB, nullable=True),
        sa.Column("face_match", JSONB, nullable=True),
        sa.Column("ip_analysis", JSONB, nullable=True),
        sa.Column("risk_score", sa.Integer, nullable=True),
        sa.Column("warnings", JSONB, nullable=True),
        sa.Column("device_info", JSONB, nullable=True),
        sa.Column("face_embedding", JSONB, nullable=True),
        sa.Column("reviewer", sa.String, nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "verification_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("verification_id", UUID(as_uuid=False), index=True),
        sa.Column("event", sa.String, nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("verification_id", UUID(as_uuid=False), index=True, nullable=True),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("target_url", sa.String, nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("request_payload", JSONB, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("attempt", sa.Integer, server_default="1"),
    )

    op.create_table(
        "review_queue",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("verification_id", UUID(as_uuid=False), index=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("status", sa.String, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

def downgrade() -> None:
    op.drop_table("review_queue")
    op.drop_table("webhook_deliveries")
    op.drop_table("verification_events")
    op.drop_table("verifications")
