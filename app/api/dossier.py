"""GET /dossier/{user_id} — dossier state for BFF."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import Verification
from app.models.response import DocumentInfo, DossierResponse, LivenessInfo

router = APIRouter()


@router.get("/dossier/{user_id}", response_model=DossierResponse)
async def get_dossier(
    user_id: str,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> DossierResponse:
    # Fetch all verifications for this user
    stmt = (
        select(Verification)
        .where(Verification.user_id == user_id)
        .order_by(Verification.created_at.desc())
    )
    result = await db.execute(stmt)
    verifications = result.scalars().all()

    if not verifications:
        raise HTTPException(status_code=404, detail="Dossier not found")

    # Build documents list from document-type verifications
    documents: list[DocumentInfo] = []
    liveness_info: LivenessInfo | None = None
    kyc_level = 1
    overall_status = "pending"
    rejection_message: str | None = None
    latest_updated = verifications[0].updated_at

    for v in verifications:
        if v.type == "document":
            doc_type = v.doc_type or "CNI"
            documents.append(DocumentInfo(
                type=doc_type,
                status=v.status,
                date=v.created_at.isoformat(),
            ))
            if v.status == "approved":
                kyc_level = max(kyc_level, 2)
                overall_status = "approved"
            elif v.status in ("pending", "manual_review"):
                overall_status = "in_review"
            elif v.status == "rejected":
                overall_status = "rejected"
                warnings = v.warnings or []
                critical = [w for w in warnings if w.get("severity") == "critical"]
                if critical:
                    rejection_message = critical[0].get("message")

        elif v.type == "liveness":
            lm = v.liveness_metrics or {}
            liveness_info = LivenessInfo(
                status=v.status,
                date=v.created_at.isoformat(),
                score=int(lm.get("score", 0)),
            )
            if v.status == "approved":
                kyc_level = max(kyc_level, 3)

    return DossierResponse(
        user_id=user_id,
        status=overall_status,
        kyc_level=kyc_level,
        updated_at=latest_updated.isoformat(),
        documents=documents,
        liveness_info=liveness_info,
        rejection_message=rejection_message,
    )
