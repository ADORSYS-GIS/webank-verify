from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from app.main import lifespan


@patch("app.main.stop_inference_executor", new_callable=AsyncMock)
@patch("app.main.stop_verification_jobs", new_callable=AsyncMock)
@patch("app.main.close_redis", new_callable=AsyncMock)
@patch("app.main.close_db", new_callable=AsyncMock)
@patch("app.main.reconciliation_loop", new_callable=AsyncMock)
@patch("app.main.run_inference", new_callable=AsyncMock)
@patch("app.main.start_inference_executor", new_callable=AsyncMock)
@patch("app.main.recover_stale_processing_verifications", new_callable=AsyncMock)
@patch("app.main.init_db", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_lifespan_warms_models_once_before_accepting_requests(
    mock_init_db,
    mock_recover_stale,
    mock_start_executor,
    mock_run_inference,
    mock_reconciliation_loop,
    mock_close_db,
    mock_close_redis,
    mock_stop_jobs,
    mock_stop_executor,
):
    async with lifespan(FastAPI()):
        mock_init_db.assert_awaited_once()
        mock_recover_stale.assert_awaited_once()
        mock_start_executor.assert_awaited_once()
        mock_run_inference.assert_awaited_once()

    mock_close_db.assert_awaited_once()
    mock_close_redis.assert_awaited_once()
    mock_stop_jobs.assert_awaited_once()
    mock_stop_executor.assert_awaited_once()
