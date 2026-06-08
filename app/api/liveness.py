"""POST /liveness/verify — liveness + face match + risk score."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.models.request import LivenessVerifyRequest
from app.models.response import LivenessResponse
from app.services import (
    face_service,
    ip_service,
    liveness_service,
    risk_service,
    storage_service,
    webhook_service,
)
from app.services.ocr_service import DocumentFields

router = APIRouter()


def _process_liveness(check_id: str, frames: list[str]):
    """CPU-bound liveness analysis + frame upload, off the event loop."""
    liveness_result = liveness_service.analyze_frames(frames)
    frame_keys = [
        storage_service.upload_image(frame_b64, f"liveness/{check_id}", f"frame_{i}")
        for i, frame_b64 in enumerate(frames)
    ]
    return liveness_result, frame_keys


@router.post("/liveness/verify", response_model=LivenessResponse)
async def verify_liveness(
    body: LivenessVerifyRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> LivenessResponse:
    check_id = str(uuid.uuid4())
    client_ip = body.client_ip or (request.client.host if request.client else None)

    # Heavy liveness analysis + S3 upload, off the event loop.
    liveness_result, frame_keys = await run_in_threadpool(_process_liveness, check_id, body.frames)

    # Fetch latest document verification for this user to get stored embedding.
    stmt = (
        select(Verification)
        .where(Verification.user_id == body.user_id, Verification.type == "document")
        .order_by(Verification.created_at.desc())
        .limit(1)
    )
    doc_verification = (await db.execute(stmt)).scalar_one_or_none()

    # Face match: sharpest selfie frame vs the stored ID face embedding.
    face_match_result = None
    if doc_verification and doc_verification.face_embedding and body.frames:
        best_frame = body.frames[liveness_result.best_frame_index]
        face_match_result = await run_in_threadpool(
            face_service.match_against_embedding,
            best_frame,
            doc_verification.face_embedding,
        )

    # IP intelligence (async, network-bound).
    ip_analysis = await ip_service.analyze_ip(client_ip) if client_ip else None

    # Rebuild the stored document fields for risk scoring.
    doc_fields = None
    if doc_verification and doc_verification.document_fields:
        df = doc_verification.document_fields
        doc_fields = DocumentFields(
            confidence=df.get("confidence", 0),
            is_expired=df.get("is_expired", False),
            is_underage=df.get("is_underage", False),
            document_number=df.get("document_number"),
            age=df.get("age"),
        )

    risk = risk_service.compute_risk(
        liveness=liveness_result,
        face_match=face_match_result,
        document=doc_fields,
        ip=ip_analysis,
    )

    if risk.decision == "approved":
        status = "passed"
    elif risk.decision == "rejected":
        status = "failed"
    else:
        status = "pending"

    ip_payload = None
    if ip_analysis:
        ip_payload = {
            "ip": ip_analysis.ip,
            "country": ip_analysis.country,
            "country_name": ip_analysis.country_name,
            "city": ip_analysis.city,
            "isp": ip_analysis.isp,
            "is_vpn": ip_analysis.is_vpn,
            "is_proxy": ip_analysis.is_proxy,
            "is_tor": ip_analysis.is_tor,
            "risk_score": ip_analysis.risk_score,
            "risk_flags": ip_analysis.risk_flags,
        }

    verification = Verification(
        id=check_id,
        user_id=body.user_id,
        type="liveness",
        status=status,
        liveness_metrics={
            "score": liveness_result.liveness_score,
            "face_quality": liveness_result.face_quality,
            "face_occlusion": liveness_result.face_occlusion,
            "face_luminance": liveness_result.face_luminance,
            "frames_analyzed": liveness_result.frames_analyzed,
            "passed": liveness_result.passed,
            "frame_keys": frame_keys,
        },
        face_match={
            "similarity": face_match_result.similarity,
            "passed": face_match_result.passed,
            "distance": face_match_result.distance,
        } if face_match_result else None,
        ip_analysis=ip_payload,
        risk_score=int(risk.overall_score),
        warnings=[{"code": w.code, "message": w.message, "severity": w.severity} for w in risk.warnings],
    )
    db.add(verification)

    if risk.requires_manual_review:
        db.add(ReviewQueue(
            id=str(uuid.uuid4()),
            verification_id=check_id,
            user_id=body.user_id,
            type="liveness",
        ))

    db.add(VerificationEvent(
        id=str(uuid.uuid4()),
        verification_id=check_id,
        event="liveness_checked",
        payload={"score": liveness_result.liveness_score, "decision": risk.decision},
    ))
    await db.commit()

    # Auto-fire webhook if decision is clear.
    if not risk.requires_manual_review:
        event_type = "kyc.level3.approved" if risk.decision == "approved" else "kyc.level3.rejected"
        await webhook_service.send_webhook(
            event_type=event_type,
            payload={"user_id": body.user_id, "check_id": check_id, "score": liveness_result.liveness_score},
            verification_id=check_id,
            db=db,
        )

    return LivenessResponse(
        check_id=check_id,
        status=status,
        score=int(liveness_result.liveness_score),
    )
