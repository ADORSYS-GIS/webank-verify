from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.api.document import submit_document
from app.models.request import DocumentSubmitRequest
from app.services.storage_service import StorageFetchError


@patch("app.api.document.get_redis")
@patch("app.api.document.create_document_verification", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_submit_document_returns_422_and_releases_lock_for_unavailable_s3_object(
    mock_create, mock_get_redis
):
    redis = AsyncMock()
    mock_get_redis.return_value = redis
    mock_create.side_effect = StorageFetchError("missing")
    body = DocumentSubmitRequest(
        user_id="user123",
        image_uris=["s3://webank-verify/kyc/user123/front.jpg"],
        doc_type="national_id",
    )
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "test-agent"
    request.client.host = "1.2.3.4"

    with pytest.raises(HTTPException) as exc:
        await submit_document(body=body, request=request, _="key", db=AsyncMock())

    assert exc.value.status_code == 422
    redis.delete.assert_awaited_once_with("doc_submit_lock:user123")
