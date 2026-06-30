import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.api.liveness import verify_liveness
from app.models.request import LivenessVerifyRequest
from app.models.db import Verification, ReviewQueue
from app.services.liveness_service import LivenessResult
from fastapi import Request

@pytest.mark.asyncio
async def test_verify_liveness_409_no_document():
    db = AsyncMock()
    # Mock scalar_one_or_none to return None (no document found)
    db.execute.return_value.scalar_one_or_none.return_value = None
    
    body = LivenessVerifyRequest(user_id="user123", frames=[])
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
    db.execute.return_value.scalar_one_or_none.return_value = doc_v
    
    body = LivenessVerifyRequest(user_id="user123", frames=[])
    request = MagicMock(spec=Request)
    
    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=body, request=request, _="key", db=db)
        
    assert exc.value.status_code == 409
    assert "already processed" in exc.value.detail

@pytest.mark.asyncio
async def test_verify_liveness_idempotent():
    db = AsyncMock()
    doc_v = Verification(id="v1", user_id="user123", status="pending", liveness_metrics={"score": 85})
    db.execute.return_value.scalar_one_or_none.return_value = doc_v
    
    body = LivenessVerifyRequest(user_id="user123", frames=[])
    request = MagicMock(spec=Request)
    
    resp = await verify_liveness(body=body, request=request, _="key", db=db)
    
    assert resp.check_id == "v1"
    assert resp.score == 85
    assert resp.status == "pending"

@patch("app.api.liveness.run_in_threadpool")
@patch("app.api.liveness.webhook_service.send_webhook")
@patch("app.api.liveness.person_service.resolve_person_id")
@patch("app.api.liveness.risk_service.compute_risk")
@pytest.mark.asyncio
async def test_verify_liveness_auto_fire_webhook(mock_compute_risk, mock_resolve_person, mock_send_webhook, mock_run):
    db = AsyncMock()
    doc_v = Verification(id="v1", user_id="user123", status="pending")
    # First execute is for Verification, second is for ReviewQueue
    db.execute.return_value.scalar_one_or_none.side_effect = [doc_v, ReviewQueue(verification_id="v1")]
    
    mock_run.return_value = (LivenessResult(liveness_score=90), ["key1"])
    mock_compute_risk.return_value = MagicMock(decision="approved", overall_score=95, warnings=[])
    mock_resolve_person.return_value = "person123"

    body = LivenessVerifyRequest(user_id="user123", frames=["f1"])
    request = MagicMock(spec=Request)
    
    resp = await verify_liveness(body=body, request=request, _="key", db=db)
    
    assert resp.status == "approved"
    mock_send_webhook.assert_called_once()
    kwargs = mock_send_webhook.call_args.kwargs
    assert kwargs["event_type"] == "kyc.level2.approved"
    assert kwargs["payload"]["user_id"] == "user123"
    assert kwargs["payload"]["person_id"] == "person123"
    assert doc_v.status == "approved"
