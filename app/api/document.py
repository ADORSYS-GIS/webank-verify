"""POST /document/submit — OCR + face extract + queue for review."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.models.request import DocumentSubmitRequest
from app.models.response import DocSubmitResponse
from app.services import face_service, ocr_service, storage_service

router = APIRouter()


@router.post("/document/submit", response_model=DocSubmitResponse)
async def submit_document(
    body: DocumentSubmitRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> DocSubmitResponse:
    verification_id = str(uuid.uuid4())
    client_ip = body.client_ip or request.client.host if request.client else None
    user_agent = body.user_agent or request.headers.get("user-agent")

    # Determine doc type label
    doc_type = "PASSPORT" if body.doc_type == "passport" else "CNI"

    # Run OCR on front image
    front_b64 = body.images[0]
    back_b64 = body.images[1] if len(body.images) > 1 else None
    doc_fields = ocr_service.extract_from_cni(front_b64, back_b64, doc_type)

    # Extract face embedding from ID front image (for later face match)
    embedding = face_service.extract_embedding(front_b64)

    # Store images in S3
    img_keys = []
    for i, img_b64 in enumerate(body.images):
        key = storage_service.upload_image(img_b64, f"documents/{verification_id}", f"page_{i}")
        img_keys.append(key)

    # Parse user-agent
    device_info = {"user_agent": user_agent, "ip": client_ip}

    # Persist verification record
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
        device_info=device_info,
    )
    db.add(verification)

    # Add to review queue
    queue_entry = ReviewQueue(
        id=str(uuid.uuid4()),
        verification_id=verification_id,
        user_id=body.user_id,
        type="document",
    )
    db.add(queue_entry)

    # Audit event
    event = VerificationEvent(
        id=str(uuid.uuid4()),
        verification_id=verification_id,
        event="document_submitted",
        payload={"doc_type": doc_type, "ocr_confidence": doc_fields.confidence},
    )
    db.add(event)
    await db.commit()

    return DocSubmitResponse(submission_id=verification_id, status="pending")
