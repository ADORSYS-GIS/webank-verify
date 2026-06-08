"""POST /recovery/queue — queue manual recovery review."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ReviewQueue
from app.models.request import RecoveryQueueRequest

router = APIRouter()


@router.post("/recovery/queue", status_code=200)
async def queue_recovery(
    body: RecoveryQueueRequest,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    db.add(ReviewQueue(
        id=str(uuid.uuid4()),
        verification_id=str(uuid.uuid4()),
        user_id=body.user_id,
        type="recovery",
        priority=2,  # highest priority
    ))
    await db.commit()
    return JSONResponse(content={"status": "queued"})
