"""Admin REST API — operator dashboard endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import operator_identity, require_admin
from app.core.db import get_db
from app.core.config import settings
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
from app.services.document_service import enqueue_document_verification
from app.services.verification_jobs import enqueue_document_processing

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

logger = logging.getLogger(__name__)


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
            issue_date=df.get("issue_date"),
            is_expired=df.get("is_expired", False),
            age=df.get("age"),
            is_underage=df.get("is_underage", False),
            sex=df.get("sex"),
            height=df.get("height"),
            profession=df.get("profession"),
            father=df.get("father"),
            mother=df.get("mother"),
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
        webhook_delivery_status=v.webhook_delivery_status,
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

    # In the 2-level model, all verifications are Level 2 (document + liveness combined)
    # Build the webhook payload from the shared builder so all call sites stay in sync.
    event_type, payload = await webhook_service.build_webhook_payload(db, v)
    # Fire webhook in the background so the dashboard stays responsive.
    # The webhook service retries 3x with [1,5,15]s backoff (21s worst case)
    # and logs every attempt to the webhook_deliveries table.
    webhook_service.fire_webhook_background(
        event_type=event_type,
        payload=payload,
        verification_id=verification_id,
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
    # Persist the fraud flag on the verification row so the reconciler and
    # resend endpoint can rebuild the webhook payload without losing it
    # (fail-closed on fraud — see review feedback on PR #63).
    v.fraud_flag = body.fraud_flag

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

    # Build the webhook payload from the shared builder so all call sites stay in sync.
    event_type, reject_payload = await webhook_service.build_webhook_payload(db, v)
    webhook_service.fire_webhook_background(
        event_type=event_type,
        payload=reject_payload,
        verification_id=verification_id,
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


@router.post("/verifications/{verification_id}/resend-webhook")
async def resend_webhook(
    verification_id: str,
    operator: str = Depends(operator_identity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-fire the kyc.level2.approved or kyc.level2.rejected webhook.

    Used when the original webhook delivery failed (e.g. BFF was down or
    returned 4xx/5xx). The verification status in the DB is not changed —
    only the webhook is re-sent based on the current status.
    """
    result = await db.execute(select(Verification).where(Verification.id == verification_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")

    if v.status not in ("approved", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resend webhook for status '{v.status}'. Only approved/rejected records support resend.",
        )

    # Build the webhook payload from the shared builder so the fraud_flag
    # and first_name/last_name are preserved on redelivery (review feedback).
    event_type, payload = await webhook_service.build_webhook_payload(db, v)

    db.add(VerificationEvent(
        verification_id=verification_id,
        event="webhook_resent",
        payload={"operator": operator, "event_type": event_type},
    ))
    # Reset status to pending while the new delivery is in-flight
    v.webhook_delivery_status = "pending"
    await db.commit()

    webhook_service.fire_webhook_background(
        event_type=event_type,
        payload=payload,
        verification_id=verification_id,
    )

    return {"status": "queued", "event_type": event_type, "verification_id": verification_id}


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


# Maximum file size for uploads (10MB)
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024

# Allowed MIME types for document uploads
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

def _verify_magic_bytes(content: bytes, content_type: str) -> bool:
    """Verify that file bytes match the claimed content type (OWASP A03)."""
    if content_type == "image/jpeg" and content.startswith(b"\xFF\xD8\xFF"):
        return True
    if content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if content_type == "image/webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return True
    return False


@router.post("/verifications/create")
async def create_verification(
    user_id: str = Form(..., description="User ID for the verification"),
    document_type: str = Form(..., description="Document type: 'CNI' or 'PASSPORT'"),
    front_image: UploadFile = File(..., description="Front image of the document"),
    back_image: UploadFile | None = File(None, description="Back image of the document (optional)"),
    operator: str = Depends(operator_identity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a verification record from admin-uploaded document images.

    This endpoint is used for the WhatsApp verification path where an admin
    collects documents via WhatsApp chat and creates the verification manually.

    Security:
    - Max file size: 10MB per image
    - Allowed MIME types: image/jpeg, image/png, image/webp
    - Filename is sanitized (UUID generated, client name ignored)
    """
    # Validate document type
    doc_type_upper = document_type.upper()
    if doc_type_upper not in ("CNI", "PASSPORT"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type: {document_type}. Must be 'CNI' or 'PASSPORT'",
        )

    # Validate MIME type for front image
    if front_image.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type for front_image: {front_image.content_type}. "
            f"Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Read and validate front image
    front_content = await front_image.read()
    if len(front_content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"front_image exceeds maximum size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
        )
    if not _verify_magic_bytes(front_content, front_image.content_type):
        raise HTTPException(
            status_code=400,
            detail="front_image content does not match claimed MIME type",
        )

    # Process back image if provided
    image_contents = [(front_content, front_image.content_type)]
    # Check if back_image actually has content
    if back_image and getattr(back_image, "size", 0) > 0:
        # Validate MIME type for back image
        if back_image.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type for back_image: {back_image.content_type}. "
                f"Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
            )

        back_content = await back_image.read()
        if len(back_content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"back_image exceeds maximum size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
            )
        if not _verify_magic_bytes(back_content, back_image.content_type):
            raise HTTPException(
                status_code=400,
                detail="back_image content does not match claimed MIME type",
            )

        image_contents.append((back_content, back_image.content_type))

    # Map document type to the expected input format
    # The document_service expects 'national_id' for CNI and 'passport' for PASSPORT
    doc_type_input = "passport" if doc_type_upper == "PASSPORT" else "national_id"

    # Store the operator-uploaded images, then use the same S3 URI processing
    # path as the BFF flow. This keeps documents visible in the admin dossier.
    verification_id = str(uuid.uuid4())
    image_uris = []
    for index, (content, content_type) in enumerate(image_contents):
        key = storage_service.upload_bytes(
            content,
            f"documents/{verification_id}",
            f"page_{index}",
            content_type or "image/jpeg",
        )
        image_uris.append(f"s3://{settings.s3_bucket}/{key}")

    # Persist the processing state first; OCR/face inference runs outside the
    # request worker just like the BFF-facing document endpoint.
    verification, _ = await enqueue_document_verification(
        db=db,
        user_id=user_id,
        doc_type_input=doc_type_input,
        client_ip=None,  # Admin-initiated, no client IP
        user_agent=f"admin/{operator}",
        operator=operator,
    )

    await db.commit()
    enqueue_document_processing(
        verification_id=verification.id,
        image_uris=image_uris,
        doc_type_input=doc_type_input,
        client_ip=None,
        user_agent=f"admin/{operator}",
    )

    return {
        "verification_id": verification.id,
        "status": verification.status,
        "doc_type": verification.doc_type,
        "user_id": verification.user_id,
    }
