"""Shared document processing logic for BFF and admin endpoints."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.services import face_service, ip_service, mrz_service, ocr_service, risk_service, storage_service
from app.services.ocr_service import DocumentFields, _compute_age, _parse_date

if TYPE_CHECKING:
    from app.services.ip_service import IPAnalysisResult
    from app.services.risk_service import RiskResult

# Redis key prefix for the per-user document submission mutex.
# TTL is 3 minutes — long enough to cover the slowest OCR run (typically 30–60s).
_DOC_SUBMIT_LOCK_PREFIX = "doc_submit_lock:"
_DOC_SUBMIT_LOCK_TTL = 180  # seconds


# Maps the BFF's ``doc_type`` input to the stored canonical type. Passport is the
# only MRZ-bearing type; CNI and récépissé share the French OCR pipeline.
DOC_TYPE_MAP = {"passport": "PASSPORT", "recepisse": "RECEPISSE"}


def _mrz_to_fields(mrz: mrz_service.MRZFields, doc_type: str) -> DocumentFields:
    """Map parsed MRZ fields onto the common DocumentFields shape."""
    fields = DocumentFields(
        type=doc_type,
        first_name=mrz.first_name,
        last_name=mrz.last_name,
        date_of_birth=mrz.date_of_birth,
        document_number=mrz.document_number,
        expiry_date=mrz.expiry_date,
        # A valid MRZ checksum is strong evidence the read was correct.
        confidence=0.95 if mrz.is_valid_checksum else 0.4,
    )
    if mrz.date_of_birth and (dob := _parse_date(mrz.date_of_birth)):
        fields.age = _compute_age(dob)
        fields.is_underage = fields.age < 18
    if mrz.expiry_date and (exp := _parse_date(mrz.expiry_date)):
        from datetime import date  # noqa: PLC0415

        fields.is_expired = exp < date.today()
    return fields


def process_document_images(
    verification_id: str,
    images: list[str],
    doc_type: str,
    doc_type_input: str,
) -> tuple[DocumentFields, list[float] | None, list[str]]:
    """CPU-bound pipeline (OCR/MRZ + face embedding + S3 upload).

    Runs in a worker thread so it never blocks the event loop.
    Returns (DocumentFields, embedding, image_keys).
    """
    front_b64 = images[0]
    back_b64 = images[1] if len(images) > 1 else None

    doc_fields: DocumentFields | None = None
    if doc_type_input == "passport":
        mrz = mrz_service.extract_from_passport(front_b64)
        if mrz:
            doc_fields = _mrz_to_fields(mrz, doc_type)
    if doc_fields is None:
        # CNI, or passport whose MRZ could not be read — fall back to OCR.
        doc_fields = ocr_service.extract_from_cni(front_b64, back_b64, doc_type)

    embedding = face_service.extract_embedding(front_b64)

    img_keys = []
    for i, img_b64 in enumerate(images):
        img_keys.append(
            storage_service.upload_image(img_b64, f"documents/{verification_id}", f"page_{i}")
        )

    return doc_fields, embedding, img_keys


async def create_document_verification(
    db: AsyncSession,
    user_id: str,
    images: list[str],
    doc_type_input: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
    verification_id: str | None = None,
    operator: str | None = None,
) -> Verification:
    """Create a document verification record with OCR, face extraction, and risk scoring.

    This is the shared logic used by both the BFF endpoint and the admin create endpoint.

    Args:
        db: Database session
        user_id: User ID for the verification
        images: List of base64-encoded images (front required, back optional)
        doc_type_input: Document type ('national_id', 'recepisse', or 'passport')
        client_ip: Optional client IP for IP intelligence
        user_agent: Optional user agent string
        verification_id: Optional verification ID (generated if not provided)
        operator: Optional operator ID if created by an admin

    Returns:
        The created Verification record
    """
    if verification_id is None:
        verification_id = str(uuid.uuid4())

    # Récépissé is OCR'd via the same French CNI pipeline; identity continuity
    # across récépissé→CNI is handled by the biometric person_id, not doc_type
    # (ADR 0005 / 0007). Anything unrecognized falls back to CNI.
    doc_type = DOC_TYPE_MAP.get(doc_type_input, "CNI")

    # ── Distributed mutex: prevent concurrent duplicate submissions ────────────
    # The OCR pipeline takes 30–60 s. Without a mutex, two concurrent requests
    # both pass the "no pending record" check before either commits, producing
    # two rows. We use a Redis SET NX lock keyed by user_id. The second request
    # spins for up to _DOC_SUBMIT_LOCK_TTL seconds and then re-checks the DB.
    #
    # Admin-created verifications (operator is set) skip the mutex because
    # operators intentionally create multiple records for the same user over time.
    redis = get_redis()
    lock_key = _DOC_SUBMIT_LOCK_PREFIX + user_id
    acquired = False

    if not operator:
        # Try to acquire the lock (NX = only set if not exists, EX = TTL in seconds).
        acquired = await redis.set(lock_key, verification_id, nx=True, ex=_DOC_SUBMIT_LOCK_TTL)
        if not acquired:
            # Another request is already processing OCR for this user.
            # Poll until it finishes (lock released) then return whatever it created.
            for _ in range(_DOC_SUBMIT_LOCK_TTL * 2):  # poll every 0.5 s
                await asyncio.sleep(0.5)
                still_locked = await redis.exists(lock_key)
                if not still_locked:
                    break
            # Lock gone — the first request finished. Return the record it created.
            existing_stmt = (
                select(Verification)
                .where(
                    Verification.user_id == user_id,
                    Verification.type == "document",
                    Verification.status.in_(["pending", "manual_review"]),
                )
                .order_by(Verification.created_at.desc())
                .limit(1)
            )
            existing = (await db.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                return existing
            # Fallback: lock expired before we got it — proceed to create a new record.

    # Fast-path check (lock is held by us): still return early if somehow a
    # pending record already exists (e.g., from an older submission that wasn't
    # cleaned up, or an admin-created record for the same user).
    if not operator:
        existing_stmt = (
            select(Verification)
            .where(
                Verification.user_id == user_id,
                Verification.type == "document",
                Verification.status.in_(["pending", "manual_review"]),
            )
            .order_by(Verification.created_at.desc())
            .limit(1)
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            # Release the lock before returning.
            await redis.delete(lock_key)
            return existing

    # Import here to avoid circular dependency
    from fastapi.concurrency import run_in_threadpool

    # Heavy OCR/face/upload work, off the event loop.
    doc_fields, embedding, img_keys = await run_in_threadpool(
        process_document_images, verification_id, images, doc_type, doc_type_input
    )

    # IP intelligence (async, network-bound).
    ip_analysis: IPAnalysisResult | None = (
        await ip_service.analyze_ip(client_ip) if client_ip else None
    )

    # Duplicate-face detection against previously approved users.
    # NOTE: loads approved embeddings into memory; fine at current scale, but
    # should move to a vector index if the approved set grows large.
    duplicate_user_ids: list[str] = []
    if embedding:
        stmt = select(Verification.user_id, Verification.face_embedding).where(
            Verification.type == "document",
            Verification.status == "approved",
            Verification.user_id != user_id,
            Verification.face_embedding.isnot(None),
        )
        rows = (await db.execute(stmt)).all()
        existing = [(uid, emb) for uid, emb in rows if emb]
        duplicate_user_ids = face_service.check_duplicate(embedding, existing)

    # Build operator-facing warnings (document, IP, duplicate). The document
    # flow stays "pending" for manual review — the auto-decision happens later
    # at the liveness stage — so we keep the warnings but no aggregate score.
    risk: RiskResult = risk_service.compute_risk(
        liveness=None,
        face_match=None,
        document=doc_fields,
        ip=ip_analysis,
        duplicate_user_ids=duplicate_user_ids or None,
    )
    warnings_payload = [
        {"code": w.code, "message": w.message, "severity": w.severity} for w in risk.warnings
    ]
    has_critical = any(w["severity"] == "critical" for w in warnings_payload)

    ip_payload = None
    if ip_analysis:
        ip_payload = {
            "ip": ip_analysis.ip,
            "country": ip_analysis.country,
            "country_name": ip_analysis.country_name,
            "city": ip_analysis.city,
            "isp": ip_analysis.isp,
            "is_vpn": ip_analysis.is_vpn,
            "is_proxy": ip_analysis.is_proxy,
            "is_tor": ip_analysis.is_tor,
            "risk_score": ip_analysis.risk_score,
            "risk_flags": ip_analysis.risk_flags,
        }

    verification = Verification(
        id=verification_id,
        user_id=user_id,
        type="document",
        status="pending",
        doc_type=doc_type,
        document_fields={
            "type": doc_fields.type,
            "first_name": doc_fields.first_name,
            "last_name": doc_fields.last_name,
            "date_of_birth": doc_fields.date_of_birth,
            "birth_place": doc_fields.birth_place,
            "document_number": doc_fields.document_number,
            "expiry_date": doc_fields.expiry_date,
            "issue_date": doc_fields.issue_date,
            "is_expired": doc_fields.is_expired,
            "age": doc_fields.age,
            "is_underage": doc_fields.is_underage,
            "sex": doc_fields.sex,
            "height": doc_fields.height,
            "profession": doc_fields.profession,
            "father": doc_fields.father,
            "mother": doc_fields.mother,
            "confidence": doc_fields.confidence,
            "image_keys": img_keys,
        },
        face_embedding=embedding,
        ip_analysis=ip_payload,
        warnings=warnings_payload,
        device_info={"user_agent": user_agent, "ip": client_ip},
    )
    db.add(verification)

    db.add(
        ReviewQueue(
            id=str(uuid.uuid4()),
            verification_id=verification_id,
            user_id=user_id,
            type="document",
            priority=1 if has_critical else 0,
        )
    )

    db.add(
        VerificationEvent(
            verification_id=verification_id,
            event="document_submitted",
            payload={
                "doc_type": doc_type,
                "ocr_confidence": doc_fields.confidence,
                "duplicate_user_ids": duplicate_user_ids,
                "source": "admin_create" if operator else "user_submission",
                "operator": operator,
            },
        )
    )

    return verification