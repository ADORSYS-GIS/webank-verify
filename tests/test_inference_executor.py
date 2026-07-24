import asyncio
import time

import pytest

from app.services.inference_executor import (
    run_inference,
    start_inference_executor,
    stop_inference_executor,
)


def _slow_cpu_boundary() -> str:
    time.sleep(0.05)
    return "done"


@pytest.mark.asyncio
async def test_inference_executor_keeps_event_loop_responsive():
    await start_inference_executor()
    try:
        job = asyncio.create_task(run_inference(_slow_cpu_boundary))
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.01)
        assert await job == "done"
    finally:
        await stop_inference_executor()
