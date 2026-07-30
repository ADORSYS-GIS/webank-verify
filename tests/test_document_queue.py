from unittest.mock import AsyncMock, patch

import pytest

from app.services.document_service import enqueue_document_verification


@patch("app.services.document_service.get_redis")
@pytest.mark.asyncio
async def test_enqueue_document_releases_mutex_when_db_setup_fails(mock_get_redis):
    redis = AsyncMock()
    redis.set.return_value = True
    mock_get_redis.return_value = redis
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await enqueue_document_verification(
            db=db,
            user_id="user123",
            doc_type_input="national_id",
        )

    redis.delete.assert_awaited_once_with("doc_submit_lock:user123")
