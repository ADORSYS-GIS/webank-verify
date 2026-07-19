"""POST /document/submit — OCR + face extract + queue for review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.core.redis import get_redis
from app.models.request import DocumentSubmitRequest
from app.models.response import DocSubmitResponse
from app.services.document_service import _DOC_SUBMIT_LOCK_PREFIX, create_document_verification
from app.services.storage_service import StorageFetchError

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

    redis = get_redis()
    try:
        verification = await create_document_verification(
            db=db,
            user_id=body.user_id,
            image_uris=body.image_uris,
            doc_type_input=body.doc_type,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        await db.commit()
    except (StorageFetchError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to retrieve submitted document image from storage",
        ) from exc
    finally:
        # Release the per-user mutex after either committing or failing so a
        # deleted/denied S3 object cannot block later submissions until its TTL.
        await redis.delete(_DOC_SUBMIT_LOCK_PREFIX + body.user_id)

    return DocSubmitResponse(submission_id=verification.id, status="pending")
