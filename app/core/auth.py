import hmac

from fastapi import Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.redis import get_redis

_api_key_header = APIKeyHeader(name="X-KYC-Api-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)

# Brute-force guard: lock an IP out of an auth surface after too many *failed*
# attempts within the window. Only failures are counted, so legitimate
# service-to-service traffic (all from one BFF IP) is never throttled.
_MAX_FAILURES = 10
_WINDOW_SECONDS = 60


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _reject_if_locked(request: Request, scope: str) -> None:
    key = f"authfail:{scope}:{_client_ip(request)}"
    try:
        failures = int(await get_redis().get(key) or 0)
    except Exception:
        return  # fail open if Redis is unavailable
    if failures >= _MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts; try again later",
        )


async def _record_failure(request: Request, scope: str) -> None:
    key = f"authfail:{scope}:{_client_ip(request)}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _WINDOW_SECONDS)
    except Exception:
        return  # fail open if Redis is unavailable


def _matches(provided: str | None, expected: str) -> bool:
    if provided is None:
        return False
    return hmac.compare_digest(provided, expected)


async def require_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str:
    await _reject_if_locked(request, "api_key")
    if not _matches(api_key, settings.kyc_api_key):
        await _record_failure(request, "api_key")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key  # type: ignore[return-value]


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    await _reject_if_locked(request, "admin")
    provided = credentials.credentials if credentials else None
    if not _matches(provided, settings.admin_secret):
        await _record_failure(request, "admin")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return provided  # type: ignore[return-value]


async def operator_identity(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> str:
    """Identity of the dashboard operator performing an action, for the audit
    trail. Falls back to a generic label when the header is absent."""
    return (x_operator_id or "").strip() or "operator"
