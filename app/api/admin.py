"""Admin REST API — operator dashboard endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import operator_identity, require_admin
from app.core.db import get_db
from app.models.db import Verification, VerificationEvent, WebhookDelivery
from app.models.request import AdminApproveRequest, AdminRejectRequest
from app.models.response import (
    AdminStats,
    VerificationDetail,
    VerificationListItem,
    VerificationListResponse,
    WebhookDelivery as WebhookDeliveryResponse,
)
from app.services import person_service, storage_service, webhook_service

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _to_list_item(v: Verification) -> VerificationListItem:
    warnings = v.warnings or []
    return VerificationListItem(
        id=v.id,
        user_id=v.user_id,
        status=v.status,
        doc_type=v.doc_type,
        country=v.country,
        risk_score=v.risk_score,
        warning_count=len(warnings),
        created_at=v.created_at,
    )


def _to_detail(v: Verification) -> VerificationDetail:
    from app.models.response import (  # noqa: PLC0415
        DocumentFields, FaceMatchResult, IPAnalysis, LivenessMetrics,
        VerificationDecision, Warning,
    )

    doc = None
    if v.document_fields:
        df = v.document_fields
        doc = DocumentFields(
            type=df.get("type", ""),
            first_name=df.get("first_name"),
            last_name=df.get("last_name"),
            date_of_birth=df.get("date_of_birth"),
            birth_place=df.get("birth_place"),
            document_number=df.get("document_number"),
            expiry_date=df.get("expiry_date"),
            is_expired=df.get("is_expired", False),
            age=df.get("age"),
            is_underage=df.get("is_underage", False),
            confidence=df.get("confidence", 0.0),
        )

    liveness = None
    if v.liveness_metrics:
        lm = v.liveness_metrics
        liveness = LivenessMetrics(
            score=lm.get("score", 0),
            face_quality=lm.get("face_quality", 0),
            face_occlusion=lm.get("face_occlusion", 0),
            face_luminance=lm.get("face_luminance", 0),
            frames_analyzed=lm.get("frames_analyzed", 0),
            passed=lm.get("passed", False),
        )

    face = None
    if v.face_match:
        fm = v.face_match
        face = FaceMatchResult(
            similarity=fm.get("similarity", 0),
            passed=fm.get("passed", False),
            distance=fm.get("distance", 1.0),
        )

    ip = None
    if v.ip_analysis:
        ia = v.ip_analysis
        ip = IPAnalysis(
            ip=ia.get("ip", ""),
            country=ia.get("country"),
            country_name=ia.get("country_name"),
            city=ia.get("city"),
            isp=ia.get("isp"),
            is_vpn=ia.get("is_vpn", False),
            is_proxy=ia.get("is_proxy", False),
            is_tor=ia.get("is_tor", False),
            risk_score=ia.get("risk_score", 0),
            risk_flags=ia.get("risk_flags", []),
        )

    warnings = [Warning(**w) for w in (v.warnings or [])]
    decision = VerificationDecision(result=v.status, requires_manual_review=v.status == "manual_review")

    return VerificationDetail(
        id=v.id,
        user_id=v.user_id,
        type=v.type,
        status=v.status,
        doc_type=v.doc_type,
        country=v.country,
        person_id=v.person_id,
        risk_score=v.risk_score,
        warnings=warnings,
        document=doc,
        liveness=liveness,
        face_match=face,
        ip_intelligence=ip,
        device_info=v.device_info,
        decision=decision,
        reviewer=v.reviewer,
        review_notes=v.review_notes,
        reviewed_at=v.reviewed_at,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.get("/verifications", response_model=VerificationListResponse)
async def list_verifications(
    status: str | None = Query(None),
    doc_type: str | None = Query(None),
    country: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> VerificationListResponse:
    stmt = select(Verification).order_by(Verification.created_at.desc())
    if status:
        stmt = stmt.where(Verification.status == status)
    if doc_type:
        stmt = stmt.where(Verification.doc_type == doc_type)
    if country:
        stmt = stmt.where(Verification.country == country)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    verifications = result.scalars().all()

    return VerificationListResponse(
        items=[_to_list_item(v) for v in verifications],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/verifications/{verification_id}", response_model=VerificationDetail)
async def get_verification(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
) -> VerificationDetail:
    result = await db.execute(select(Verification).where(Verification.id == verification_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _to_detail(v)


@router.post("/verifications/{verification_id}/approve")
async def approve_verification(
    verification_id: str,
    body: AdminApproveRequest,
    operator: str = Depends(operator_identity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Verification).where(Verification.id == verification_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")

    v.status = "approved"
    v.reviewer = operator
    v.review_notes = body.notes
    v.reviewed_at = datetime.now(timezone.utc)

    # Assign a stable biometric person_id now that this document identity is
    # part of the approved set (ADR 0005). Stays None when no face was extracted.
    if v.type == "document":
        v.person_id = await person_service.assign_person_id(db, v)

    db.add(VerificationEvent(
        verification_id=verification_id,
        event="operator_approved",
        payload={"reviewer": operator, "notes": body.notes, "person_id": v.person_id},
    ))
    await db.commit()

    # Determine correct webhook event based on verification type
    event_type = "kyc.level2.approved" if v.type == "document" else "kyc.level3.approved"
    payload = {"user_id": v.user_id, "verification_id": verification_id}
    # Attach the stable identity key for downstream dedup. For non-document
    # approvals (level3) resolve it from the user's approved document dossier.
    # Omitted when unknown — consumers must fail closed (ADR 0005).
    person_id = v.person_id or await person_service.resolve_person_id(db, v.user_id)
    if person_id:
        payload["person_id"] = person_id
    await webhook_service.send_webhook(
        event_type=event_type,
        payload=payload,
        verification_id=verification_id,
        db=db,
    )

    return {"status": "approved", "verification_id": verification_id, "person_id": v.person_id}


@router.post("/verifications/{verification_id}/reject")
async def reject_verification(
    verification_id: str,
    body: AdminRejectRequest,
    operator: str = Depends(operator_identity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Verification).where(Verification.id == verification_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")

    v.status = "rejected"
    v.reviewer = operator
    v.review_notes = body.reason
    v.reviewed_at = datetime.now(timezone.utc)

    # Add rejection reason to warnings
    warnings = list(v.warnings or [])
    warnings.append({"code": "OPERATOR_REJECTED", "message": body.reason, "severity": "critical"})
    v.warnings = warnings

    db.add(VerificationEvent(
        verification_id=verification_id,
        event="operator_rejected",
        payload={"reviewer": operator, "reason": body.reason, "fraud_flag": body.fraud_flag},
    ))
    await db.commit()

    event_type = "kyc.level2.rejected" if v.type == "document" else "kyc.level3.rejected"
    await webhook_service.send_webhook(
        event_type=event_type,
        payload={
            "user_id": v.user_id,
            "verification_id": verification_id,
            "reason": body.reason,
            "fraud_flag": body.fraud_flag,
        },
        verification_id=verification_id,
        db=db,
    )

    return {"status": "rejected", "verification_id": verification_id}


@router.get("/verifications/{verification_id}/frames")
async def get_frames(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Verification).where(Verification.id == verification_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")

    urls: list[str] = []
    keys: list[str] = []
    if v.liveness_metrics and v.liveness_metrics.get("frame_keys"):
        keys = v.liveness_metrics["frame_keys"]
    elif v.document_fields and v.document_fields.get("image_keys"):
        keys = v.document_fields["image_keys"]

    for key in keys:
        try:
            url = storage_service.get_presigned_url(key)
            urls.append(url)
        except Exception:
            pass

    return {"verification_id": verification_id, "urls": urls}


@router.get("/stats", response_model=AdminStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async def count_by_status(status: str) -> int:
        r = await db.execute(select(func.count()).where(Verification.status == status))
        return r.scalar_one()

    async def count_by_status_today(status: str) -> int:
        r = await db.execute(
            select(func.count()).where(
                Verification.status == status,
                Verification.reviewed_at >= today_start,
            )
        )
        return r.scalar_one()

    total_r = await db.execute(select(func.count()).select_from(Verification))

    return AdminStats(
        total=total_r.scalar_one(),
        pending=await count_by_status("pending"),
        approved=await count_by_status("approved"),
        rejected=await count_by_status("rejected"),
        manual_review=await count_by_status("manual_review"),
        approved_today=await count_by_status_today("approved"),
        rejected_today=await count_by_status_today("rejected"),
    )


@router.get("/webhooks/{verification_id}")
async def get_webhooks(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.verification_id == verification_id)
        .order_by(WebhookDelivery.delivered_at.desc())
    )
    deliveries = result.scalars().all()

    return [
        WebhookDeliveryResponse(
            id=d.id,
            event_type=d.event_type,
            target_url=d.target_url,
            http_status=d.http_status,
            attempt=d.attempt,
            delivered_at=d.delivered_at,
        )
        for d in deliveries
    ]
