"""FastAPI application — webank-verify identity verification service."""

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import admin, document, health, identity, liveness
from app.core.config import settings
from app.core.db import close_db, init_db
from app.core.redis import close_redis
from app.services.inference_executor import (
    run_inference,
    start_inference_executor,
    stop_inference_executor,
    warm_models,
)
from app.services.reconciliation_service import reconciliation_loop
from app.services.verification_jobs import (
    recover_stale_processing_verifications,
    stop_verification_jobs,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reconcile_task: asyncio.Task[None] | None = None
    try:
        # Startup
        settings.validate_secrets()
        await init_db()
        await recover_stale_processing_verifications()
        await start_inference_executor()
        await run_inference(warm_models)
        # Start the webhook reconciliation background task.
        # It retries any approved/rejected verifications where the BFF webhook
        # delivery failed (e.g. BFF was down or returned 4xx/5xx).
        reconcile_task = asyncio.create_task(reconciliation_loop())
        yield
    finally:
        # Cleanup also runs when startup/warmup fails, which matters for
        # uvicorn --reload where a failed generation is replaced immediately.
        if reconcile_task is not None:
            reconcile_task.cancel()
            try:
                await reconcile_task
            except asyncio.CancelledError:
                pass
        await stop_verification_jobs()
        await stop_inference_executor()
        await close_db()
        await close_redis()


app = FastAPI(
    title="webank-verify",
    description="Identity verification microservice for Cameroon",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,
    redoc_url="/redoc" if settings.is_dev else None,
)

_dev_origins = ["http://localhost:5173", "http://localhost:8070", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_dev_origins if settings.is_dev else ["https://webank.cm"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# BFF-facing routes
app.include_router(document.router, tags=["BFF"])
app.include_router(liveness.router, tags=["BFF"])
app.include_router(identity.router, tags=["BFF"])
app.include_router(health.router, tags=["Internal"])

# Admin dashboard API
app.include_router(admin.router, tags=["Admin"])

# Serve React dashboard static files at /admin
dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if dashboard_dist.exists():
    app.mount("/admin", StaticFiles(directory=str(dashboard_dist), html=True), name="dashboard")
