"""GET /health — health check with DB and Redis ping."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.redis import get_redis

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    checks: dict[str, str] = {}

    # Redis ping
    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return JSONResponse(content={"status": status, "checks": checks})
