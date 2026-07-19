"""Process-local executor for CPU-heavy KYC inference.

The API handlers must never run OCR, ArcFace, or OpenCV analysis on the
uvicorn event loop.  A single worker is intentional: the ML stack is large,
the CPU is already saturated by one real document, and serialising work keeps
the health endpoint responsive while providing predictable resource usage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None
_io_executor: ThreadPoolExecutor | None = None


async def start_inference_executor() -> None:
    """Create the executors once per uvicorn process."""
    global _executor, _io_executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=settings.inference_workers,
            thread_name_prefix="kyc-inference",
        )
    if _io_executor is None:
        # S3 HEAD validation must remain fast even while the inference worker
        # is occupied by a large document.
        _io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kyc-storage")


async def stop_inference_executor() -> None:
    """Stop accepting queued work during application shutdown."""
    global _executor, _io_executor
    executor, io_executor = _executor, _io_executor
    _executor = None
    _io_executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
    if io_executor is not None:
        io_executor.shutdown(wait=False, cancel_futures=True)


async def run_inference(function: Callable[..., T], /, *args: Any) -> T:
    """Run CPU-bound ML work outside the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, function, *args)


async def run_storage_io(function: Callable[..., T], /, *args: Any) -> T:
    """Run blocking S3 validation without queueing behind inference."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_io_executor, function, *args)


def warm_models() -> None:
    """Load and execute every local ML path once on the inference worker."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    from app.services import face_service, liveness_service, ocr_service  # noqa: PLC0415

    image = np.full((160, 160, 3), 127, dtype=np.uint8)
    encoded, buffer = cv2.imencode(".jpg", image)
    if not encoded:
        raise RuntimeError("Unable to build KYC model warmup image")
    sample = buffer.tobytes()

    logger.info("Warming KYC OCR, face, and liveness models on inference worker")
    # These calls intentionally perform a dummy inference, not merely imports,
    # so lazy torch/TensorFlow initialisation happens before the first request.
    ocr_service.extract_from_cni(sample, doc_type="CNI")
    face_service.warm_model(sample)
    liveness_service.analyze_frames([sample])
    logger.info("KYC model warmup complete")
