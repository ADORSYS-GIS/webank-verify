"""POST /liveness/verify — liveness + face match + risk score.

In the 2-level KYC model, this endpoint UPDATES the existing document verification
record with liveness data instead of creating a new separate liveness record.
The combined document+liveness verification is then reviewed by an operator
(or auto-approved/rejected based on risk score).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
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
    person_service,
    risk_service,
    storage_service,
    webhook_service,
)
from app.services.ocr_service import DocumentFields

router = APIRouter()


def _process_liveness(verification_id: str, frames: list[str]):
    """CPU-bound liveness analysis + frame upload, off the event loop."""
    liveness_result = liveness_service.analyze_frames(frames)
    frame_keys = [
        storage_service.upload_image(
            frame_b64, f"verifications/{verification_id}/liveness", f"frame_{i}"
        )
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
    client_ip = body.client_ip or (request.client.host if request.client else None)

    # Fetch the latest document verification for this user with row-level lock
    # to prevent race conditions from concurrent liveness submissions.
    stmt = (
        select(Verification)
        .where(Verification.user_id == body.user_id, Verification.type == "document")
        .order_by(Verification.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    doc_verification = (await db.execute(stmt)).scalar_one_or_none()

    # Edge case: No document verification found
    if not doc_verification:
        raise HTTPException(
            status_code=409,
            detail="No document verification found — submit ID documents first",
        )

    # Edge case: Document already processed (approved or rejected)
    if doc_verification.status in ("approved", "rejected"):
        raise HTTPException(
            status_code=409,
            detail="Document verification already processed — submit new documents first",
        )

    # Idempotency: If liveness already processed, return existing result
    if doc_verification.liveness_metrics is not None:
        return LivenessResponse(
            check_id=doc_verification.id,
            status=doc_verification.status,
            score=doc_verification.liveness_metrics.get("score", 0),
        )

    # Heavy liveness analysis + S3 upload, off the event loop.
    liveness_result, frame_keys = await run_in_threadpool(
        _process_liveness, doc_verification.id, body.frames
    )

    # Face match: sharpest selfie frame vs the stored ID face embedding.
    face_match_result = None
    if doc_verification.face_embedding and body.frames:
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
    if doc_verification.document_fields:
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

    # Map risk decision to verification status
    if risk.decision == "approved":
        status = "approved"
    elif risk.decision == "rejected":
        status = "rejected"
    else:
        status = "manual_review"

    # Build IP analysis payload
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

    # Merge liveness warnings with existing document warnings
    existing_warnings = list(doc_verification.warnings or [])
    liveness_warnings = [
        {"code": w.code, "message": w.message, "severity": w.severity}
        for w in risk.warnings
    ]
    # Deduplicate warnings by code
    warning_codes = {w["code"] for w in existing_warnings}
    merged_warnings = existing_warnings + [
        w for w in liveness_warnings if w["code"] not in warning_codes
    ]

    # UPDATE the existing document verification record
    doc_verification.liveness_metrics = {
        "score": liveness_result.liveness_score,
        "face_quality": liveness_result.face_quality,
        "face_occlusion": liveness_result.face_occlusion,
        "face_luminance": liveness_result.face_luminance,
        "frames_analyzed": liveness_result.frames_analyzed,
        "passed": liveness_result.passed,
        "frame_keys": frame_keys,
    }
    doc_verification.face_match = (
        {
            "similarity": face_match_result.similarity,
            "passed": face_match_result.passed,
            "distance": face_match_result.distance,
        }
        if face_match_result
        else None
    )
    # Replace or merge IP analysis (liveness IP supersedes document IP)
    doc_verification.ip_analysis = ip_payload
    doc_verification.risk_score = int(risk.overall_score)
    doc_verification.warnings = merged_warnings
    doc_verification.status = status

    # Add verification event for liveness check
    db.add(
        VerificationEvent(
            verification_id=doc_verification.id,
            event="liveness_checked",
            payload={
                "score": liveness_result.liveness_score,
                "decision": risk.decision,
                "face_match_similarity": face_match_result.similarity
                if face_match_result
                else None,
            },
        )
    )

    # Update the existing ReviewQueue entry
    queue_stmt = (
        select(ReviewQueue)
        .where(ReviewQueue.verification_id == doc_verification.id)
        .with_for_update()
    )
    queue_entry = (await db.execute(queue_stmt)).scalar_one_or_none()
    if queue_entry:
        queue_entry.type = "complete"  # Signals liveness data is now available
        if status == "manual_review":
            queue_entry.priority = 1  # Bump priority for manual review cases

    await db.commit()

    # Auto-fire webhook if decision is clear (approved or rejected)
    # For manual_review, the webhook fires when operator approves/rejects
    if status in ("approved", "rejected"):
        event_type = (
            "kyc.level2.approved" if status == "approved" else "kyc.level2.rejected"
        )
        payload = {
            "user_id": body.user_id,
            "verification_id": doc_verification.id,
            "score": liveness_result.liveness_score,
        }
        # Attach the stable identity key from the user's approved document
        # dossier so downstream dedup works (ADR 0005). Omitted when unknown —
        # consumers must fail closed.
        person_id = await person_service.resolve_person_id(db, body.user_id)
        if person_id:
            payload["person_id"] = person_id
        await webhook_service.send_webhook(
            event_type=event_type,
            payload=payload,
            verification_id=doc_verification.id,
            db=db,
        )

    return LivenessResponse(
        check_id=doc_verification.id,
        status=status,
        score=int(liveness_result.liveness_score),
    )