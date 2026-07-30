from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.api.document import submit_document
from app.models.db import Verification
from app.models.request import DocumentSubmitRequest
from app.services.storage_service import StorageFetchError


def _request() -> MagicMock:
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "test-agent"
    request.client.host = "1.2.3.4"
    return request


@patch("app.api.document.enqueue_document_processing")
@patch("app.api.document.release_document_submission_lock", new_callable=AsyncMock)
@patch("app.api.document.enqueue_document_verification", new_callable=AsyncMock)
@patch("app.api.document.run_storage_io", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_submit_document_queues_work_and_returns_202_immediately(
    mock_storage, mock_enqueue, mock_release, mock_dispatch
):
    verification = Verification(id="v1", user_id="user123", type="document", status="processing")
    mock_enqueue.return_value = verification, True
    body = DocumentSubmitRequest(
        user_id="user123",
        image_uris=["s3://webank-verify/kyc/user123/front.jpg"],
        doc_type="national_id",
    )
    db = AsyncMock()

    response = await submit_document(body=body, request=_request(), _="key", db=db)

    assert response.verification_id == "v1"
    assert response.status == "processing"
    mock_storage.assert_awaited_once()
    db.commit.assert_awaited_once()
    mock_release.assert_awaited_once_with("user123")
    mock_dispatch.assert_called_once()
    assert mock_dispatch.call_args.kwargs["verification_id"] == "v1"


@patch("app.api.document.enqueue_document_verification", new_callable=AsyncMock)
@patch("app.api.document.run_storage_io", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_submit_document_returns_422_for_unavailable_s3_object(mock_storage, mock_enqueue):
    mock_storage.side_effect = StorageFetchError("missing")
    body = DocumentSubmitRequest(
        user_id="user123",
        image_uris=["s3://webank-verify/kyc/user123/front.jpg"],
        doc_type="national_id",
    )

    with pytest.raises(HTTPException) as exc:
        await submit_document(body=body, request=_request(), _="key", db=AsyncMock())

    assert exc.value.status_code == 422
    mock_enqueue.assert_not_awaited()
