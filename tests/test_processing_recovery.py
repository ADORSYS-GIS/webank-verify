from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.db import ReviewQueue, Verification
from app.services.verification_jobs import (
    _mark_processing_failed,
    recover_stale_processing_verifications,
)


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ScalarRowsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


def _session(db):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@patch("app.services.verification_jobs.AsyncSessionLocal")
@pytest.mark.asyncio
async def test_startup_recovery_marks_processing_jobs_reviewable(mock_factory):
    document = Verification(
        id="doc-1", user_id="user-1", type="document", status="processing"
    )
    liveness = Verification(
        id="live-1",
        user_id="user-2",
        type="document",
        status="processing",
        liveness_metrics={"status": "processing"},
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        ScalarRowsResult([document, liveness]),
        ScalarResult(ReviewQueue(verification_id="doc-1")),
        ScalarResult(None),
    ]
    mock_factory.return_value = _session(db)

    recovered = await recover_stale_processing_verifications()

    assert recovered == 2
    assert document.status == "manual_review"
    assert liveness.status == "manual_review"
    assert liveness.liveness_metrics == {"status": "failed"}
    db.commit.assert_awaited_once()


@patch("app.services.verification_jobs.AsyncSessionLocal")
@pytest.mark.asyncio
async def test_liveness_failure_clears_processing_marker(mock_factory):
    verification = Verification(
        id="v1",
        user_id="user-1",
        type="document",
        status="processing",
        liveness_metrics={"status": "processing"},
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [ScalarResult(verification), ScalarResult(None)]
    mock_factory.return_value = _session(db)

    await _mark_processing_failed("v1", "liveness", RuntimeError("frame missing"))

    assert verification.status == "manual_review"
    assert verification.liveness_metrics == {"status": "failed"}
    assert verification.warnings[0]["code"] == "LIVENESS_PROCESSING_FAILED"
