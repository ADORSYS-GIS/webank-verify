from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_api_key_header = APIKeyHeader(name="X-KYC-Api-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    if api_key != settings.kyc_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key


async def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    if credentials is None or credentials.credentials != settings.admin_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return credentials.credentials
