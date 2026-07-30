"""POST /document/submit — accept a document and queue off-thread inference."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.request import DocumentSubmitRequest
from app.models.response import AcceptedVerificationResponse
from app.services.document_service import (
    enqueue_document_verification,
    release_document_submission_lock,
)
from app.services.inference_executor import run_storage_io
from app.services.storage_service import StorageFetchError, validate_objects
from app.services.verification_jobs import enqueue_document_processing

router = APIRouter()


@router.post(
    "/document/submit",
    response_model=AcceptedVerificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_document(
    body: DocumentSubmitRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> AcceptedVerificationResponse:
    client_ip = body.client_ip or (request.client.host if request.client else None)
    user_agent = body.user_agent or request.headers.get("user-agent")
    created = False

    try:
        # Validate the submitted S3 objects synchronously, but never do that
        # blocking boto3 I/O on the event loop or behind a long ML job.
        await run_storage_io(validate_objects, body.image_uris)
        verification, created = await enqueue_document_verification(
            db=db,
            user_id=body.user_id,
            doc_type_input=body.doc_type,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
    except (StorageFetchError, ValueError) as exc:
        if created:
            await release_document_submission_lock(body.user_id)
        raise HTTPException(
            status_code=422,
            detail="Unable to retrieve submitted document image from storage",
        ) from exc
    except Exception:
        if created:
            await release_document_submission_lock(body.user_id)
        raise
    else:
        if created:
            await release_document_submission_lock(body.user_id)

    if created:
        enqueue_document_processing(
            verification_id=verification.id,
            image_uris=body.image_uris,
            doc_type_input=body.doc_type,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    return AcceptedVerificationResponse(verification_id=verification.id, status="processing")
