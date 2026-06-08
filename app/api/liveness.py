"""POST /liveness/verify — liveness + face match + risk score."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_api_key
from app.core.db import get_db
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.models.request import LivenessVerifyRequest
from app.models.response import LivenessResponse
from app.services import face_service, liveness_service, risk_service, storage_service, webhook_service

router = APIRouter()


@router.post("/liveness/verify", response_model=LivenessResponse)
async def verify_liveness(
    body: LivenessVerifyRequest,
    request: Request,
    _: str = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> LivenessResponse:
    check_id = str(uuid.uuid4())

    # Run liveness analysis
    liveness_result = liveness_service.analyze_frames(body.frames)

    # Store frames in S3 + use best frame for face match
    frame_keys = []
    for i, frame_b64 in enumerate(body.frames):
        key = storage_service.upload_image(frame_b64, f"liveness/{check_id}", f"frame_{i}")
        frame_keys.append(key)

    # Fetch latest document verification for this user to get stored embedding
    stmt = (
        select(Verification)
        .where(Verification.user_id == body.user_id, Verification.type == "document")
        .order_by(Verification.created_at.desc())
        .limit(1)
    )
    doc_result = await db.execute(stmt)
    doc_verification = doc_result.scalar_one_or_none()

    # Face match: selfie (best frame) vs stored ID face embedding
    face_match_result = None
    if doc_verification and doc_verification.face_embedding and body.frames:
        best_frame = body.frames[0]  # first frame is usually best quality
        face_match_result = face_service.compare_faces(
            id_img_b64=best_frame,  # fallback: compare frames vs stored embedding
            selfie_b64=best_frame,
        )
        # Use embedding comparison directly if we have stored embedding
        selfie_emb = face_service.extract_embedding(body.frames[0])
        if selfie_emb and doc_verification.face_embedding:
            sim = 1.0 - face_service._cosine_similarity(selfie_emb, doc_verification.face_embedding)
            similarity_pct = max(0.0, (1.0 - sim) * 100)
            from app.services.face_service import FaceMatchResult, SIMILARITY_THRESHOLD  # noqa: PLC0415
            face_match_result = FaceMatchResult(
                similarity=round(similarity_pct, 2),
                passed=similarity_pct / 100 >= (1.0 - SIMILARITY_THRESHOLD),
                distance=round(sim, 4),
            )

    # Compute risk
    doc_fields = None
    if doc_verification and doc_verification.document_fields:
        from app.services.ocr_service import DocumentFields  # noqa: PLC0415
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
        ip=None,
    )

    # Determine status
    if risk.decision == "approved":
        status = "passed"
    elif risk.decision == "rejected":
        status = "failed"
    else:
        status = "pending"

    # Persist
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
            "similarity": face_match_result.similarity if face_match_result else None,
            "passed": face_match_result.passed if face_match_result else None,
            "distance": face_match_result.distance if face_match_result else None,
        } if face_match_result else None,
        risk_score=int(risk.overall_score),
        warnings=[{"code": w.code, "message": w.message, "severity": w.severity} for w in risk.warnings],
    )
    db.add(verification)

    # Queue for manual review if needed
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

    # Auto-fire webhook if decision is clear
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
