"""POST /document/submit — OCR + face extract + queue for review."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.models.request import DocumentSubmitRequest
from app.models.response import DocSubmitResponse
from app.services import (
    face_service,
    ip_service,
    mrz_service,
    ocr_service,
    risk_service,
    storage_service,
)
from app.services.ocr_service import DocumentFields, _compute_age, _parse_date

router = APIRouter()


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


def _process_document(verification_id: str, images: list[str], doc_type: str, doc_type_input: str):
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


@router.post("/document/submit", response_model=DocSubmitResponse)
async def submit_document(
    body: DocumentSubmitRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> DocSubmitResponse:
    verification_id = str(uuid.uuid4())
    client_ip = body.client_ip or (request.client.host if request.client else None)
    user_agent = body.user_agent or request.headers.get("user-agent")

    doc_type = "PASSPORT" if body.doc_type == "passport" else "CNI"

    # Heavy OCR/face/upload work, off the event loop.
    doc_fields, embedding, img_keys = await run_in_threadpool(
        _process_document, verification_id, body.images, doc_type, body.doc_type
    )

    # IP intelligence (async, network-bound).
    ip_analysis = await ip_service.analyze_ip(client_ip) if client_ip else None

    # Duplicate-face detection against previously approved users.
    # NOTE: loads approved embeddings into memory; fine at current scale, but
    # should move to a vector index if the approved set grows large.
    duplicate_user_ids: list[str] = []
    if embedding:
        stmt = select(Verification.user_id, Verification.face_embedding).where(
            Verification.type == "document",
            Verification.status == "approved",
            Verification.user_id != body.user_id,
            Verification.face_embedding.isnot(None),
        )
        rows = (await db.execute(stmt)).all()
        existing = [(uid, emb) for uid, emb in rows if emb]
        duplicate_user_ids = face_service.check_duplicate(embedding, existing)

    # Build operator-facing warnings (document, IP, duplicate). The document
    # flow stays "pending" for manual review — the auto-decision happens later
    # at the liveness stage — so we keep the warnings but no aggregate score.
    risk = risk_service.compute_risk(
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
        user_id=body.user_id,
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
            "is_expired": doc_fields.is_expired,
            "age": doc_fields.age,
            "is_underage": doc_fields.is_underage,
            "confidence": doc_fields.confidence,
            "image_keys": img_keys,
        },
        face_embedding=embedding,
        ip_analysis=ip_payload,
        warnings=warnings_payload,
        device_info={"user_agent": user_agent, "ip": client_ip},
    )
    db.add(verification)

    db.add(ReviewQueue(
        id=str(uuid.uuid4()),
        verification_id=verification_id,
        user_id=body.user_id,
        type="document",
        priority=1 if has_critical else 0,
    ))

    db.add(VerificationEvent(
        id=str(uuid.uuid4()),
        verification_id=verification_id,
        event="document_submitted",
        payload={
            "doc_type": doc_type,
            "ocr_confidence": doc_fields.confidence,
            "duplicate_user_ids": duplicate_user_ids,
        },
    ))
    await db.commit()

    return DocSubmitResponse(submission_id=verification_id, status="pending")
