"""FastAPI application — webank-verify identity verification service."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import admin, document, dossier, health, liveness, professional, recovery
from app.core.config import settings
from app.core.db import close_db, init_db
from app.core.redis import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_dev else ["https://webank.cm"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# BFF-facing routes
app.include_router(document.router, tags=["BFF"])
app.include_router(liveness.router, tags=["BFF"])
app.include_router(dossier.router, tags=["BFF"])
app.include_router(professional.router, tags=["BFF"])
app.include_router(recovery.router, tags=["BFF"])
app.include_router(health.router, tags=["Internal"])

# Admin dashboard API
app.include_router(admin.router, tags=["Admin"])

# Serve React dashboard static files at /admin
dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if dashboard_dist.exists():
    app.mount("/admin", StaticFiles(directory=str(dashboard_dist), html=True), name="dashboard")
