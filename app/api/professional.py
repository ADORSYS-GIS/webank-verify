"""POST /professional/submit, GET /professional/status/{user_id} — KYC4 dossier."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ProfessionalDossier, ReviewQueue
from app.models.request import ProfessionalSubmitRequest
from app.models.response import ProfessionalDossierResponse

router = APIRouter()


@router.post("/professional/submit", response_model=ProfessionalDossierResponse)
async def submit_professional(
    body: ProfessionalSubmitRequest,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalDossierResponse:
    now = datetime.now(timezone.utc)

    # Check if dossier already exists
    stmt = select(ProfessionalDossier).where(ProfessionalDossier.user_id == body.user_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Re-submission: reset to pending
        existing.professional_type = body.professional_type
        existing.status = "pending"
        existing.documents = body.documents
        existing.metadata_ = body.metadata
        existing.submitted_at = now
        existing.rejection_reason = None
        dossier = existing
    else:
        dossier = ProfessionalDossier(
            id=str(uuid.uuid4()),
            user_id=body.user_id,
            professional_type=body.professional_type,
            status="pending",
            documents=body.documents,
            metadata_=body.metadata,
        )
        db.add(dossier)

    # Queue for operator review
    db.add(ReviewQueue(
        id=str(uuid.uuid4()),
        verification_id=dossier.id,
        user_id=body.user_id,
        type="professional",
        priority=1,  # higher priority
    ))
    await db.commit()

    return ProfessionalDossierResponse(
        user_id=body.user_id,
        professional_type=body.professional_type,
        status=dossier.status,
        submitted_at=dossier.submitted_at.isoformat(),
    )


@router.get("/professional/status/{user_id}", response_model=ProfessionalDossierResponse)
async def get_professional_status(
    user_id: str,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalDossierResponse:
    stmt = select(ProfessionalDossier).where(ProfessionalDossier.user_id == user_id)
    result = await db.execute(stmt)
    dossier = result.scalar_one_or_none()

    if not dossier:
        raise HTTPException(status_code=404, detail="Professional dossier not found")

    return ProfessionalDossierResponse(
        user_id=user_id,
        professional_type=dossier.professional_type,
        status=dossier.status,
        submitted_at=dossier.submitted_at.isoformat() if dossier.submitted_at else None,
        reviewed_at=dossier.reviewed_at.isoformat() if dossier.reviewed_at else None,
        rejection_reason=dossier.rejection_reason,
    )
