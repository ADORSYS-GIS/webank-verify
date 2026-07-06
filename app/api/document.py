"""POST /document/submit — OCR + face extract + queue for review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.core.redis import get_redis
from app.models.request import DocumentSubmitRequest
from app.models.response import DocSubmitResponse
from app.services.document_service import _DOC_SUBMIT_LOCK_PREFIX, create_document_verification

router = APIRouter()


@router.post("/document/submit", response_model=DocSubmitResponse)
async def submit_document(
    body: DocumentSubmitRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> DocSubmitResponse:
    client_ip = body.client_ip or (request.client.host if request.client else None)
    user_agent = body.user_agent or request.headers.get("user-agent")

    verification = await create_document_verification(
        db=db,
        user_id=body.user_id,
        images=body.images,
        doc_type_input=body.doc_type,
        client_ip=client_ip,
        user_agent=user_agent,
    )

    await db.commit()

    # Release the per-user mutex AFTER commit so any concurrent retry that
    # was waiting on the lock will find the committed row in the DB.
    redis = get_redis()
    await redis.delete(_DOC_SUBMIT_LOCK_PREFIX + body.user_id)

    return DocSubmitResponse(submission_id=verification.id, status="pending")
