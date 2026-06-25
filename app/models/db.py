import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # document | liveness | complete
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str] = mapped_column(String, default="CM")
    # Stable biometric identity key (ADR 0005). Assigned on document approval by
    # clustering the face embedding against already-approved identities; reused
    # across a person's accounts/documents so downstream consumers can dedup on
    # UNIQUE(person_id). Null until approved (or when no face was extracted).
    person_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    document_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    liveness_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_match: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    device_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class VerificationEvent(Base):
    __tablename__ = "verification_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    verification_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    verification_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    target_url: Mapped[str | None] = mapped_column(String, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    attempt: Mapped[int] = mapped_column(Integer, default=1)


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    verification_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProfessionalDossier(Base):
    __tablename__ = "professional_dossiers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    professional_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    documents: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
