"""Background reconciliation job for failed webhook deliveries.

Runs every 60 seconds. Finds all approved/rejected verifications where
webhook_delivery_status = 'failed' and re-fires the webhook automatically.
This ensures that transient BFF outages (network blip, restart, bad API key
that was since fixed) don't leave users permanently stuck at Level 1.

The job is idempotent: it only retries 'failed' records, not 'pending' ones
(which may still be in-flight). After each retry the status is updated to
'delivered' or remains 'failed' depending on the outcome.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

logger = logging.getLogger(__name__)

# How often the reconciliation loop runs (seconds)
RECONCILE_INTERVAL = 60

# Maximum number of records to reconcile per run (safety cap)
RECONCILE_BATCH_SIZE = 20


async def _reconcile_once() -> None:
    """Run one reconciliation pass."""
    from app.core.db import AsyncSessionLocal  # noqa: PLC0415
    from app.models.db import Verification, VerificationEvent  # noqa: PLC0415
    from app.services import webhook_service  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        # Find failed-delivery records that are approved or rejected
        stmt = (
            select(Verification)
            .where(
                Verification.webhook_delivery_status == "failed",
                Verification.status.in_(["approved", "rejected"]),
            )
            .order_by(Verification.reviewed_at.asc())
            .limit(RECONCILE_BATCH_SIZE)
        )
        result = await session.execute(stmt)
        stale = result.scalars().all()

    if not stale:
        return

    logger.info("[reconciler] Found %d verification(s) with failed webhook — retrying", len(stale))

    for v in stale:
        try:
            # Build the webhook payload from the shared builder so the
            # fraud_flag and first_name/last_name are preserved on
            # redelivery (review feedback on PR #63).
            async with AsyncSessionLocal() as session:
                event_type, payload = await webhook_service.build_webhook_payload(session, v)

            async with AsyncSessionLocal() as session:
                # Mark as pending so we don't double-retry while in-flight
                result = await session.execute(
                    select(Verification).where(Verification.id == v.id)
                )
                record = result.scalar_one_or_none()
                if not record or record.webhook_delivery_status != "failed":
                    continue  # Already retried by another path (e.g. manual resend)

                record.webhook_delivery_status = "pending"
                session.add(VerificationEvent(
                    verification_id=v.id,
                    event="webhook_reconciled",
                    payload={"event_type": event_type, "auto": True},
                ))
                await session.commit()

            # Attempt delivery
            async with AsyncSessionLocal() as session:
                delivered = await webhook_service.send_webhook(
                    event_type=event_type,
                    payload=payload,
                    verification_id=v.id,
                    db=session,
                )

            # Write outcome back
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Verification).where(Verification.id == v.id)
                )
                record = result.scalar_one_or_none()
                if record:
                    record.webhook_delivery_status = "delivered" if delivered else "failed"
                    await session.commit()

            if delivered:
                logger.info(
                    "[reconciler] Successfully delivered %s for verification %s",
                    event_type, v.id,
                )
            else:
                logger.warning(
                    "[reconciler] Re-delivery still failing for verification %s — will retry next cycle",
                    v.id,
                )

        except Exception:
            logger.exception(
                "[reconciler] Unexpected error reconciling verification %s", v.id
            )


async def reconciliation_loop() -> None:
    """Infinite loop that reconciles failed webhook deliveries every RECONCILE_INTERVAL seconds.

    Designed to run as a background asyncio task started at app startup.
    Exits cleanly on CancelledError (i.e. app shutdown).
    """
    logger.info(
        "[reconciler] Starting webhook reconciliation loop (interval=%ds, batch=%d)",
        RECONCILE_INTERVAL, RECONCILE_BATCH_SIZE,
    )
    while True:
        try:
            await asyncio.sleep(RECONCILE_INTERVAL)
            await _reconcile_once()
        except asyncio.CancelledError:
            logger.info("[reconciler] Reconciliation loop cancelled — shutting down")
            return
        except Exception:
            logger.exception("[reconciler] Unexpected error in reconciliation loop — continuing")
