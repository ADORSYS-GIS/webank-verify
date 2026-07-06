"""HMAC-SHA256 signed webhook delivery with retry and audit logging.

Also provides the single source of truth for building kyc.level2 webhook
payloads (``build_webhook_payload``) and a background fire-and-record helper
(``fire_webhook_background``) shared by all call sites: admin approve/reject/
resend, liveness auto-approve/reject, and the reconciliation loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# Strong references to in-flight background webhook tasks so the GC doesn't
# collect them mid-delivery (asyncio.create_task only holds a weak ref).
_background_tasks: set[asyncio.Task] = set()


def _serialize(payload: dict) -> str:
    """Canonical JSON body. The exact string returned here is BOTH signed and
    transmitted, so the receiver can verify the HMAC over the raw request body."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _sign_body(body: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ── Payload builder (single source of truth) ───────────────────────────────

async def build_webhook_payload(db: AsyncSession, v) -> tuple[str, dict]:
    """Build the (event_type, payload) for a verification based on its status.

    Used by all four call sites — admin approve/reject, admin resend, liveness
    auto-approve/reject, and the reconciliation loop — so the payload can never
    drift between them (previous bugs: missing first_name/last_name in the
    reconciler, hardcoded fraud_flag=False in resend/reconciler).

    Expects ``v`` to be a ``Verification`` row with ``status``, ``person_id``,
    ``document_fields``, ``warnings``, and ``fraud_flag`` already populated.
    """
    from app.services import person_service  # noqa: PLC0415

    if v.status == "approved":
        event_type = "kyc.level2.approved"
        payload: dict = {"user_id": v.user_id, "verification_id": v.id}
        # Attach the stable identity key for downstream dedup (ADR 0005).
        # Omitted when unknown — consumers must fail closed.
        person_id = v.person_id or await person_service.resolve_person_id(db, v.user_id)
        if person_id:
            payload["person_id"] = person_id
        # Include the verified name from OCR so the BFF can update Keycloak
        # and the Redis contact index without a separate API call.
        if v.document_fields:
            first_name = v.document_fields.get("first_name") or ""
            last_name = v.document_fields.get("last_name") or ""
            if first_name:
                payload["first_name"] = first_name
            if last_name:
                payload["last_name"] = last_name
    else:
        event_type = "kyc.level2.rejected"
        # Pull rejection reason from warnings if available
        reason = ""
        if v.warnings:
            for w in v.warnings:
                if isinstance(w, dict) and w.get("code") == "OPERATOR_REJECTED":
                    reason = w.get("message", "")
                    break
        payload = {
            "user_id": v.user_id,
            "verification_id": v.id,
            "reason": reason,
            "fraud_flag": v.fraud_flag,
        }

    return event_type, payload


# ── Background fire-and-record (shared by all call sites) ───────────────────

def fire_webhook_background(
    event_type: str,
    payload: dict,
    verification_id: str,
) -> None:
    """Fire a webhook in the background with its own DB session.

    After all attempts complete, writes the final delivery status
    (delivered / failed) back to the verification record so the
    dashboard can surface a warning banner when delivery fails, and
    the reconciliation job can retry on failure.

    Retains a strong reference to the asyncio task so the GC doesn't
    collect it mid-flight.
    """
    task = asyncio.create_task(_fire_and_record(event_type, payload, verification_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _fire_and_record(
    event_type: str,
    payload: dict,
    verification_id: str,
) -> None:
    from app.core.db import AsyncSessionLocal  # noqa: PLC0415
    from app.models.db import Verification  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        try:
            delivered = await send_webhook(
                event_type=event_type,
                payload=payload,
                verification_id=verification_id,
                db=session,
            )
            # Write delivery outcome back to the verification row
            result = await session.execute(
                select(Verification).where(Verification.id == verification_id)
            )
            v = result.scalar_one_or_none()
            if v:
                v.webhook_delivery_status = "delivered" if delivered else "failed"
                await session.commit()
        except Exception:
            logger.exception(
                "Background webhook delivery failed for %s (verification %s)",
                event_type,
                verification_id,
            )


# ── Webhook delivery ────────────────────────────────────────────────────────

async def send_webhook(
    event_type: str,
    payload: dict,
    target_url: str | None = None,
    secret: str | None = None,
    verification_id: str | None = None,
    db=None,
) -> bool:
    """Send HMAC-SHA256 signed webhook with up to 3 attempts.

    Returns True if any attempt is acknowledged with a 2xx status.
    Each attempt is logged as a separate row in webhook_deliveries
    (distinct delivery_id per attempt so history is never overwritten).
    """
    url = target_url or settings.webhook_url
    key = secret or settings.webhook_secret

    # Build the signed envelope once — all retry attempts share the same
    # envelope id so the BFF can deduplicate on it.
    envelope_id = str(uuid.uuid4())
    envelope = {
        "id": envelope_id,
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    body = _serialize(envelope)
    signature = _sign_body(body, key)

    max_attempts = 3
    backoff_seconds = [1, 5, 15]

    for attempt in range(1, max_attempts + 1):
        # Each attempt gets its own delivery row (unique id) so history is
        # append-only and no row is ever silently overwritten on retry.
        delivery_id = str(uuid.uuid4())
        http_status: int | None = None
        response_body: str | None = None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webank-Signature": signature,
                        "X-Webank-Event": event_type,
                        # Let the BFF deduplicate on the envelope id
                        "X-Webank-Delivery-Id": envelope_id,
                    },
                )
                http_status = resp.status_code
                response_body = resp.text[:500]

        except Exception as exc:
            response_body = str(exc)[:500]

        finally:
            if db:
                await _log_delivery(
                    db, delivery_id, verification_id, event_type, url,
                    http_status, envelope, response_body, attempt,
                )

        if http_status is not None and 200 <= http_status < 300:
            return True

        if attempt < max_attempts:
            await asyncio.sleep(backoff_seconds[attempt - 1])

    return False


async def _log_delivery(
    db,
    delivery_id: str,
    verification_id: str | None,
    event_type: str,
    url: str,
    http_status: int | None,
    payload: dict,
    response_body: str | None,
    attempt: int,
) -> None:
    from app.models.db import WebhookDelivery  # noqa: PLC0415

    entry = WebhookDelivery(
        id=delivery_id,
        verification_id=verification_id,
        event_type=event_type,
        target_url=url,
        http_status=http_status,
        request_payload=payload,
        response_body=response_body,
        attempt=attempt,
    )
    db.add(entry)
    try:
        await db.commit()
    except Exception:
        await db.rollback()