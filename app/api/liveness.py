"""POST /liveness/verify — accept frames and queue off-thread analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import Verification, VerificationEvent
from app.models.request import LivenessVerifyRequest
from app.models.response import AcceptedVerificationResponse
from app.services.inference_executor import run_storage_io
from app.services.storage_service import StorageFetchError, validate_objects
from app.services.verification_jobs import enqueue_liveness_processing

router = APIRouter()


@router.post(
    "/liveness/verify",
    response_model=AcceptedVerificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def verify_liveness(
    body: LivenessVerifyRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> AcceptedVerificationResponse:
    """Persist the queued state, then return before OpenCV/ArcFace runs."""
    client_ip = body.client_ip or (request.client.host if request.client else None)
    document = (
        await db.execute(
            select(Verification)
            .where(Verification.user_id == body.user_id, Verification.type == "document")
            .order_by(Verification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(
            status_code=409,
            detail="No document verification found — submit ID documents first",
        )
    if document.status in ("approved", "rejected"):
        raise HTTPException(
            status_code=409,
            detail="Document verification already processed — submit new documents first",
        )
    if document.status == "manual_review" and not document.document_fields:
        raise HTTPException(
            status_code=409,
            detail="Document verification requires manual review before liveness can run",
        )
    if document.liveness_metrics is not None:
        # The same row is the idempotency key for an already queued/completed
        # liveness request. A completed manual-review decision must not be
        # presented to the BFF as if fresh work had been queued.
        if document.liveness_metrics.get("status") == "processing":
            return AcceptedVerificationResponse(verification_id=document.id, status="processing")
        raise HTTPException(
            status_code=409,
            detail="Liveness verification already processed — submit new documents first",
        )

    try:
        await run_storage_io(validate_objects, body.frame_uris)
    except (StorageFetchError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to retrieve submitted liveness frame from storage",
        ) from exc

    document.liveness_metrics = {"status": "processing"}
    db.add(
        VerificationEvent(
            verification_id=document.id,
            event="liveness_queued",
            payload={"frame_count": len(body.frame_uris)},
        )
    )
    await db.commit()
    enqueue_liveness_processing(document.id, body.frame_uris, client_ip)
    return AcceptedVerificationResponse(verification_id=document.id, status="processing")
