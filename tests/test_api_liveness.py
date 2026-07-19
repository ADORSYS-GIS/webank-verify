import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.api.liveness import verify_liveness
from app.models.request import LivenessVerifyRequest
from app.models.db import Verification, ReviewQueue
from app.services.liveness_service import LivenessResult
from fastapi import Request

class MockResult:
    def __init__(self, values):
        self.values = values if isinstance(values, list) else [values]
    def scalar_one_or_none(self):
        return self.values.pop(0) if self.values else None

@pytest.mark.asyncio
async def test_verify_liveness_409_no_document():
    db = AsyncMock()
    db.execute.return_value = MockResult(None)
    
    body = LivenessVerifyRequest(user_id="user123", frame_uris=["s3://webank-verify/kyc/user123/f1.jpg"])
    request = MagicMock(spec=Request)
    request.client.host = "1.2.3.4"

    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=body, request=request, _="key", db=db)
    
    assert exc.value.status_code == 409
    assert "No document verification found" in exc.value.detail

@pytest.mark.asyncio
async def test_verify_liveness_409_already_processed():
    db = AsyncMock()
    doc_v = Verification(id="v1", user_id="user123", status="approved")
    db.execute.return_value = MockResult(doc_v)
    
    body = LivenessVerifyRequest(user_id="user123", frame_uris=["s3://webank-verify/kyc/user123/f1.jpg"])
    request = MagicMock(spec=Request)
    
    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=body, request=request, _="key", db=db)
        
    assert exc.value.status_code == 409
    assert "already processed" in exc.value.detail

@pytest.mark.asyncio
async def test_verify_liveness_idempotent():
    db = AsyncMock()
    doc_v = Verification(id="v1", user_id="user123", status="pending", liveness_metrics={"score": 85})
    db.execute.return_value = MockResult(doc_v)
    
    body = LivenessVerifyRequest(user_id="user123", frame_uris=["s3://webank-verify/kyc/user123/f1.jpg"])
    request = MagicMock(spec=Request)
    
    resp = await verify_liveness(body=body, request=request, _="key", db=db)
    
    assert resp.check_id == "v1"
    assert resp.score == 85
    assert resp.status == "pending"

@patch("app.api.liveness.run_in_threadpool")
@patch("app.api.liveness.webhook_service.build_webhook_payload", new_callable=AsyncMock)
@patch("app.api.liveness.webhook_service.fire_webhook_background")
@patch("app.api.liveness.person_service.assign_person_id", new_callable=AsyncMock)
@patch("app.api.liveness.risk_service.compute_risk")
@pytest.mark.asyncio
async def test_verify_liveness_auto_fire_webhook(
    mock_compute_risk, mock_assign_person_id, mock_fire_background, mock_build_payload, mock_run
):
    """Auto-approved liveness must assign person_id and fire webhook in background."""
    db = AsyncMock()
    db.add = MagicMock()
    doc_v = Verification(id="v1", user_id="user123", status="pending")
    # First execute is for Verification, second is for ReviewQueue
    db.execute.return_value = MockResult([doc_v, ReviewQueue(verification_id="v1")])
    
    mock_run.return_value = (LivenessResult(liveness_score=90, frames_analyzed=1), ["key1"], [b"frame"])
    mock_compute_risk.return_value = MagicMock(decision="approved", overall_score=95, warnings=[])
    mock_assign_person_id.return_value = "person123"
    mock_build_payload.return_value = (
        "kyc.level2.approved",
        {"user_id": "user123", "verification_id": "v1", "person_id": "person123"},
    )

    body = LivenessVerifyRequest(user_id="user123", frame_uris=["s3://webank-verify/kyc/user123/f1.jpg"])
    request = MagicMock(spec=Request)
    
    resp = await verify_liveness(body=body, request=request, _="key", db=db)
    
    assert resp.status == "approved"
    # person_id must be assigned on auto-approve (ADR 0005)
    mock_assign_person_id.assert_called_once()
    assert doc_v.person_id == "person123"
    # Webhook must be fired in the background (not inline)
    mock_build_payload.assert_called_once()
    mock_fire_background.assert_called_once()
    kwargs = mock_fire_background.call_args.kwargs
    assert kwargs["event_type"] == "kyc.level2.approved"
    assert kwargs["payload"]["person_id"] == "person123"
    assert doc_v.status == "approved"
