from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.db import ReviewQueue, Verification
from app.services.liveness_service import LivenessResult
from app.services.verification_jobs import _run_liveness_job


class MockResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@patch("app.services.verification_jobs.webhook_service.fire_webhook_background")
@patch("app.services.verification_jobs.webhook_service.build_webhook_payload", new_callable=AsyncMock)
@patch("app.services.verification_jobs.person_service.assign_person_id", new_callable=AsyncMock)
@patch("app.services.verification_jobs.risk_service.compute_risk")
@patch("app.services.verification_jobs.run_inference", new_callable=AsyncMock)
@patch("app.services.verification_jobs._wait_for_document", new_callable=AsyncMock)
@patch("app.services.verification_jobs.AsyncSessionLocal")
@pytest.mark.asyncio
async def test_liveness_job_delivers_existing_webhook_on_auto_approval(
    mock_session_factory,
    mock_wait_for_document,
    mock_run_inference,
    mock_compute_risk,
    mock_assign_person_id,
    mock_build_payload,
    mock_fire_webhook,
):
    document = Verification(
        id="v1",
        user_id="user123",
        status="pending",
        document_fields={"confidence": 0.9},
    )
    mock_wait_for_document.return_value = document
    mock_run_inference.return_value = (LivenessResult(liveness_score=90, frames_analyzed=1), ["f1"], [b"frame"])
    mock_compute_risk.return_value = MagicMock(decision="approved", overall_score=95, warnings=[])
    mock_assign_person_id.return_value = "person123"
    mock_build_payload.return_value = ("kyc.level2.approved", {"verification_id": "v1"})

    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [MockResult(document), MockResult(ReviewQueue(verification_id="v1"))]
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=db)
    session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = session

    await _run_liveness_job("v1", ["s3://webank-verify/kyc/user123/f1.jpg"], None)

    assert document.status == "approved"
    assert document.person_id == "person123"
    db.commit.assert_awaited_once()
    mock_build_payload.assert_awaited_once_with(db, document)
    mock_fire_webhook.assert_called_once_with("kyc.level2.approved", {"verification_id": "v1"}, "v1")
