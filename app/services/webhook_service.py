"""HMAC-SHA256 signed webhook delivery with retry and audit logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx

from app.core.config import settings


def _sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
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
    """
    Send HMAC-SHA256 signed webhook. Returns True if delivered successfully.
    Logs every attempt to webhook_deliveries table.
    """
    url = target_url or settings.webhook_url
    key = secret or settings.webhook_secret
    delivery_id = str(uuid.uuid4())

    envelope = {
        "id": delivery_id,
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    signature = _sign_payload(envelope, key)

    max_attempts = 3
    backoff_seconds = [1, 5, 15]

    for attempt in range(1, max_attempts + 1):
        http_status = None
        response_body = None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json=envelope,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webank-Signature": signature,
                        "X-Webank-Event": event_type,
                    },
                )
                http_status = resp.status_code
                response_body = resp.text[:500]

            if db:
                await _log_delivery(
                    db, delivery_id, verification_id, event_type, url,
                    http_status, envelope, response_body, attempt,
                )

            if 200 <= http_status < 300:
                return True

        except Exception as exc:
            response_body = str(exc)[:500]
            if db:
                await _log_delivery(
                    db, delivery_id, verification_id, event_type, url,
                    http_status, envelope, response_body, attempt,
                )

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
