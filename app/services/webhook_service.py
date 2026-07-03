"""HMAC-SHA256 signed webhook delivery with retry and audit logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx

from app.core.config import settings


def _serialize(payload: dict) -> str:
    """Canonical JSON body. The exact string returned here is BOTH signed and
    transmitted, so the receiver can verify the HMAC over the raw request body."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _sign_body(body: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


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
            import asyncio  # noqa: PLC0415
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
