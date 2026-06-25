"""GET /identity/{user_id} — stable biometric person_id for downstream dedup.

A pull alternative to the ``person_id`` carried in the KYC webhook (ADR 0005).
Lets a consumer (e.g. the webank-mobile referral anti-fraud control) ask
"who is this user, as a real person?" without any raw PII leaving this service.
Fails closed: when the user has no approved document identity, ``person_id`` is
null and ``kyc_level2_approved`` is false.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import Verification
from app.models.response import IdentityResponse
from app.services import person_service

router = APIRouter()


@router.get("/identity/{user_id}", response_model=IdentityResponse)
async def get_identity(
    user_id: str,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> IdentityResponse:
    person_id = await person_service.resolve_person_id(db, user_id)

    approved_stmt = (
        select(Verification.id)
        .where(
            Verification.user_id == user_id,
            Verification.type == "document",
            Verification.status == "approved",
        )
        .limit(1)
    )
    kyc_level2_approved = (await db.execute(approved_stmt)).scalar_one_or_none() is not None

    return IdentityResponse(
        user_id=user_id,
        person_id=person_id,
        kyc_level2_approved=kyc_level2_approved,
    )
