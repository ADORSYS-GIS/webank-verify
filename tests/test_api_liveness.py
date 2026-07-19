from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.api.liveness import verify_liveness
from app.models.db import Verification
from app.models.request import LivenessVerifyRequest
from app.services.storage_service import StorageFetchError


class MockResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def _request() -> MagicMock:
    request = MagicMock(spec=Request)
    request.client.host = "1.2.3.4"
    return request


def _body() -> LivenessVerifyRequest:
    return LivenessVerifyRequest(
        user_id="user123", frame_uris=["s3://webank-verify/kyc/user123/f1.jpg"]
    )


@pytest.mark.asyncio
async def test_verify_liveness_409_no_document():
    db = AsyncMock()
    db.execute.return_value = MockResult(None)

    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=_body(), request=_request(), _="key", db=db)

    assert exc.value.status_code == 409
    assert "No document verification found" in exc.value.detail


@pytest.mark.asyncio
async def test_verify_liveness_409_already_processed():
    db = AsyncMock()
    db.execute.return_value = MockResult(Verification(id="v1", user_id="user123", status="approved"))

    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=_body(), request=_request(), _="key", db=db)

    assert exc.value.status_code == 409
    assert "already processed" in exc.value.detail


@pytest.mark.asyncio
async def test_verify_liveness_is_idempotent_while_processing():
    db = AsyncMock()
    db.execute.return_value = MockResult(
        Verification(
            id="v1", user_id="user123", status="processing", liveness_metrics={"status": "processing"}
        )
    )

    response = await verify_liveness(body=_body(), request=_request(), _="key", db=db)

    assert response.verification_id == "v1"
    assert response.status == "processing"
    db.commit.assert_not_awaited()


@patch("app.api.liveness.run_storage_io", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_verify_liveness_returns_422_when_s3_object_is_unavailable(mock_storage):
    db = AsyncMock()
    db.execute.return_value = MockResult(Verification(id="v1", user_id="user123", status="pending"))
    mock_storage.side_effect = StorageFetchError("missing")

    with pytest.raises(HTTPException) as exc:
        await verify_liveness(body=_body(), request=_request(), _="key", db=db)

    assert exc.value.status_code == 422


@patch("app.api.liveness.enqueue_liveness_processing")
@patch("app.api.liveness.run_storage_io", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_verify_liveness_queues_work_and_returns_202(mock_storage, mock_dispatch):
    db = AsyncMock()
    db.add = MagicMock()
    document = Verification(id="v1", user_id="user123", status="pending")
    db.execute.return_value = MockResult(document)

    response = await verify_liveness(body=_body(), request=_request(), _="key", db=db)

    assert response.verification_id == "v1"
    assert response.status == "processing"
    assert document.liveness_metrics == {"status": "processing"}
    db.commit.assert_awaited_once()
    mock_dispatch.assert_called_once_with("v1", _body().frame_uris, "1.2.3.4")
