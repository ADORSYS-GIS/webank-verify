"""Stable biometric person_id assignment and resolution (ADR 0005).

A ``person_id`` is a stable identity key derived from face-embedding clustering,
NOT from a document number. A document number is unstable in real Cameroon cases
(CNI renewal issues a new number, récépissé→CNI transition, passport-vs-CNI for
diaspora), so it produces false negatives for identity dedup. The biometric key
lets downstream services (e.g. the webank-mobile referral anti-fraud control)
enforce one-reward-per-real-person via ``UNIQUE(person_id)`` without any raw PII
leaving this service.

See webank-context ADR 0005 and webank-verify#2.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Verification
from app.services import face_service


async def assign_person_id(db: AsyncSession, verification: Verification) -> str | None:
    """Assign (or reuse) a stable ``person_id`` for an approved document verification.

    The verification's face embedding is clustered against every other
    already-approved document verification that carries a ``person_id``: on a
    biometric match the existing key is reused (same real person), otherwise a
    new key is minted.

    Returns ``None`` when no face was extracted — identity is then not
    deduplicable, so the caller MUST fail closed (omit ``person_id`` from the
    webhook; downstream then treats the account as an unknown person).
    """
    embedding = verification.face_embedding
    if not embedding:
        return None

    stmt = select(Verification.person_id, Verification.face_embedding).where(
        Verification.type == "document",
        Verification.status == "approved",
        Verification.id != verification.id,
        Verification.person_id.isnot(None),
        Verification.face_embedding.isnot(None),
    )
    rows = (await db.execute(stmt)).all()
    existing_people = [(pid, emb) for pid, emb in rows if pid and emb]

    person_id, _matched = face_service.match_or_mint_person_id(embedding, existing_people)
    return person_id


async def resolve_person_id(db: AsyncSession, user_id: str) -> str | None:
    """Return the stable ``person_id`` from a user's approved document dossier.

    Used to attach the identity key to webhooks/endpoints that are not the
    document approval itself (liveness, professional/level3, the pull endpoint).
    Returns ``None`` when the user has no approved document with a ``person_id``.
    """
    stmt = (
        select(Verification.person_id)
        .where(
            Verification.user_id == user_id,
            Verification.type == "document",
            Verification.status == "approved",
            Verification.person_id.isnot(None),
        )
        .order_by(Verification.reviewed_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
