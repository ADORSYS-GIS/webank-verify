"""Background orchestration for document and liveness verification jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.db import ReviewQueue, Verification, VerificationEvent
from app.services import (
    face_service,
    ip_service,
    liveness_service,
    person_service,
    risk_service,
    webhook_service,
)
from app.services.document_service import complete_document_verification, process_document_images
from app.services.inference_executor import run_inference
from app.services.ocr_service import DocumentFields
from app.services.storage_service import StorageFetchError

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()
_DOCUMENT_WAIT_SECONDS = 300


def _track(task: asyncio.Task[None]) -> None:
    """Keep background jobs alive until completion and surface failures in logs."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def enqueue_document_processing(
    verification_id: str,
    image_uris: list[str],
    doc_type_input: str,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    _track(
        asyncio.create_task(
            _run_document_job(
                verification_id, image_uris, doc_type_input, client_ip, user_agent
            ),
            name=f"document-verification-{verification_id}",
        )
    )


def enqueue_liveness_processing(
    verification_id: str,
    frame_uris: list[str],
    client_ip: str | None,
) -> None:
    _track(
        asyncio.create_task(
            _run_liveness_job(verification_id, frame_uris, client_ip),
            name=f"liveness-verification-{verification_id}",
        )
    )


async def stop_verification_jobs() -> None:
    """Cancel orchestration tasks before disposing their database engine."""
    tasks = tuple(_background_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _background_tasks.clear()


async def _mark_processing_failed(verification_id: str, stage: str, exc: Exception) -> None:
    """Retain a reviewable record if an accepted job later cannot run."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Verification).where(Verification.id == verification_id))
        verification = result.scalar_one_or_none()
        if verification is None:
            return

        warnings = list(verification.warnings or [])
        warnings.append(
            {
                "code": f"{stage.upper()}_PROCESSING_FAILED",
                "message": "Verification processing failed and requires manual review",
                "severity": "critical",
            }
        )
        verification.warnings = warnings
        verification.status = "manual_review"
        db.add(
            VerificationEvent(
                verification_id=verification.id,
                event=f"{stage}_processing_failed",
                payload={"error": str(exc)[:500]},
            )
        )
        queue = (
            await db.execute(
                select(ReviewQueue).where(ReviewQueue.verification_id == verification.id)
            )
        ).scalar_one_or_none()
        if queue is None:
            db.add(
                ReviewQueue(
                    id=str(uuid.uuid4()),
                    verification_id=verification.id,
                    user_id=verification.user_id,
                    type="complete" if stage == "liveness" else "document",
                    priority=1,
                )
            )
        else:
            queue.priority = 1
        await db.commit()


async def _run_document_job(
    verification_id: str,
    image_uris: list[str],
    doc_type_input: str,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Verification).where(Verification.id == verification_id))
            verification = result.scalar_one_or_none()
            if verification is None or verification.status != "processing":
                return
            doc_type = verification.doc_type or "CNI"

        pipeline_result = await run_inference(
            process_document_images, image_uris, doc_type, doc_type_input
        )

        async with AsyncSessionLocal() as db:
            verification = (
                await db.execute(
                    select(Verification)
                    .where(Verification.id == verification_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if verification is None or verification.status != "processing":
                return
            await complete_document_verification(
                db=db,
                verification=verification,
                image_uris=image_uris,
                doc_type_input=doc_type_input,
                client_ip=client_ip,
                user_agent=user_agent,
                pipeline_result=pipeline_result,
            )
            await db.commit()
            logger.info("Document verification %s completed", verification_id)
    except (StorageFetchError, ValueError) as exc:
        logger.warning("Document verification %s failed: %s", verification_id, exc)
        await _mark_processing_failed(verification_id, "document", exc)
    except Exception as exc:  # keep failures observable and reviewable
        logger.exception("Document verification %s crashed", verification_id)
        await _mark_processing_failed(verification_id, "document", exc)


def _process_liveness(frame_uris: list[str]):
    """Blocking S3 fetch + OpenCV analysis, executed on the inference worker."""
    from app.services import storage_service  # noqa: PLC0415

    frame_bytes = [storage_service.fetch_bytes(uri) for uri in frame_uris]
    frame_keys = [storage_service.parse_s3_uri(uri)[1] for uri in frame_uris]
    return liveness_service.analyze_frames(frame_bytes), frame_keys, frame_bytes


async def _wait_for_document(verification_id: str) -> Verification | None:
    """Wait for the preceding document job without occupying the ML worker."""
    deadline = asyncio.get_running_loop().time() + _DOCUMENT_WAIT_SECONDS
    while True:
        async with AsyncSessionLocal() as db:
            verification = (
                await db.execute(select(Verification).where(Verification.id == verification_id))
            ).scalar_one_or_none()
            if verification is None:
                return None
            if verification.document_fields:
                return verification
            if verification.status != "processing":
                return None
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Document processing did not complete before liveness timeout")
        await asyncio.sleep(0.1)


async def _run_liveness_job(
    verification_id: str,
    frame_uris: list[str],
    client_ip: str | None,
) -> None:
    try:
        document = await _wait_for_document(verification_id)
        if document is None:
            logger.info("Skipping liveness job %s: document is not ready", verification_id)
            return

        liveness_result, frame_keys, frame_bytes = await run_inference(_process_liveness, frame_uris)
        face_match_result = None
        if document.face_embedding and frame_bytes:
            best_frame = frame_bytes[liveness_result.best_frame_index]
            face_match_result = await run_inference(
                face_service.match_against_embedding, best_frame, document.face_embedding
            )

        ip_analysis = await ip_service.analyze_ip(client_ip) if client_ip else None
        doc_fields = _document_fields_from_payload(document.document_fields)
        risk = risk_service.compute_risk(
            liveness=liveness_result,
            face_match=face_match_result,
            document=doc_fields,
            ip=ip_analysis,
        )
        status = "approved" if risk.decision == "approved" else (
            "rejected" if risk.decision == "rejected" else "manual_review"
        )

        async with AsyncSessionLocal() as db:
            record = (
                await db.execute(
                    select(Verification)
                    .where(Verification.id == verification_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if record is None:
                return
            _apply_liveness_result(
                record, liveness_result, frame_keys, face_match_result, ip_analysis, risk, status
            )
            if status == "approved":
                record.person_id = await person_service.assign_person_id(db, record)

            db.add(
                VerificationEvent(
                    verification_id=record.id,
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
            queue = (
                await db.execute(
                    select(ReviewQueue)
                    .where(ReviewQueue.verification_id == record.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if queue:
                queue.type = "complete"
                if status == "manual_review":
                    queue.priority = 1

            await db.commit()
            if status in ("approved", "rejected"):
                event_type, payload = await webhook_service.build_webhook_payload(db, record)
                webhook_service.fire_webhook_background(event_type, payload, record.id)
            logger.info("Liveness verification %s completed with %s", verification_id, status)
    except (StorageFetchError, ValueError, TimeoutError) as exc:
        logger.warning("Liveness verification %s failed: %s", verification_id, exc)
        await _mark_processing_failed(verification_id, "liveness", exc)
    except Exception as exc:  # keep failures observable and reviewable
        logger.exception("Liveness verification %s crashed", verification_id)
        await _mark_processing_failed(verification_id, "liveness", exc)


def _document_fields_from_payload(payload: dict | None) -> DocumentFields | None:
    if not payload:
        return None
    return DocumentFields(
        confidence=payload.get("confidence", 0),
        is_expired=payload.get("is_expired", False),
        is_underage=payload.get("is_underage", False),
        document_number=payload.get("document_number"),
        age=payload.get("age"),
    )


def _apply_liveness_result(
    record: Verification,
    liveness_result,
    frame_keys: list[str],
    face_match_result,
    ip_analysis,
    risk,
    status: str,
) -> None:
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
    existing_warnings = list(record.warnings or [])
    liveness_warnings = [
        {"code": warning.code, "message": warning.message, "severity": warning.severity}
        for warning in risk.warnings
    ]
    warning_codes = {warning["code"] for warning in existing_warnings}

    record.liveness_metrics = {
        "score": liveness_result.liveness_score,
        "face_quality": liveness_result.face_quality,
        "face_occlusion": liveness_result.face_occlusion,
        "face_luminance": liveness_result.face_luminance,
        "frames_analyzed": liveness_result.frames_analyzed,
        "passed": liveness_result.passed,
        "frame_keys": frame_keys,
    }
    record.face_match = (
        {
            "similarity": face_match_result.similarity,
            "passed": face_match_result.passed,
            "distance": face_match_result.distance,
        }
        if face_match_result
        else None
    )
    record.ip_analysis = ip_payload
    record.risk_score = int(risk.overall_score)
    record.warnings = existing_warnings + [
        warning for warning in liveness_warnings if warning["code"] not in warning_codes
    ]
    record.status = status
