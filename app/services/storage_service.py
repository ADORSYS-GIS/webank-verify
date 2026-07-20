"""S3-compatible storage for document images and liveness frames."""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

_client = None
_presign_client = None

logger = logging.getLogger(__name__)


class StorageFetchError(RuntimeError):
    """Raised when a submitted S3 object cannot be retrieved."""


def _get_client():
    global _client
    if _client is None:
        if not settings.s3_endpoint_url:
            raise ValueError(
                "S3_ENDPOINT_URL is not configured. "
                "Set S3_ENDPOINT_URL (e.g. http://localstack:4566) to enable document storage."
            )
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
        # Ensure bucket exists (dev only)
        try:
            _client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            _client.create_bucket(Bucket=settings.s3_bucket)
            logger.info("Created S3 bucket: %s", settings.s3_bucket)
    return _client


def _get_presign_client():
    """Return an S3 client whose endpoint is reachable from the browser.

    Uploads use the internal endpoint (``S3_ENDPOINT_URL``, e.g.
    ``http://localstack:4566``) so traffic stays on the Docker network.
    Presigned URLs are handed to the browser, which cannot resolve Docker
    service names — so we build them with ``S3_PUBLIC_URL`` when set.

    Falls back to the same client as uploads when ``S3_PUBLIC_URL`` is
    unset (single-host deployments where the browser can already reach
    ``S3_ENDPOINT_URL``).
    """
    global _presign_client
    public_url = settings.s3_public_url or settings.s3_endpoint_url
    if _presign_client is None or getattr(_presign_client, "_public_url", None) != public_url:
        if not public_url:
            raise ValueError(
                "S3_PUBLIC_URL / S3_ENDPOINT_URL is not configured. "
                "Set S3_PUBLIC_URL to a host the browser can reach "
                "(e.g. http://localhost:4566)."
            )
        _presign_client = boto3.client(
            "s3",
            endpoint_url=public_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )
        _presign_client._public_url = public_url  # type: ignore[attr-defined]
    return _presign_client


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Validate an in-bucket S3 URI and return its bucket and object key."""
    parsed = urlparse(s3_uri)
    if (
        parsed.scheme != "s3"
        or not parsed.netloc
        or not parsed.path.lstrip("/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Expected an s3://bucket/key URI")
    if parsed.netloc != settings.s3_bucket:
        raise ValueError("S3 URI bucket does not match configured storage bucket")
    return parsed.netloc, parsed.path.lstrip("/")


def fetch_bytes(s3_uri: str) -> bytes:
    """Fetch raw object bytes for a validated in-bucket ``s3://`` URI."""
    bucket, key = parse_s3_uri(s3_uri)
    try:
        response = _get_client().get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Unable to fetch submitted S3 object: bucket=%s key=%s", bucket, key)
        raise StorageFetchError("Unable to retrieve submitted image from storage") from exc


def validate_objects(s3_uris: list[str]) -> None:
    """Validate that every submitted URI points to a readable uploaded object."""
    client = _get_client()
    bucket = key = "unknown"
    try:
        for s3_uri in s3_uris:
            bucket, key = parse_s3_uri(s3_uri)
            client.head_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Unable to validate submitted S3 object: bucket=%s key=%s", bucket, key)
        raise StorageFetchError(
            f"Unable to retrieve submitted image from storage: {bucket}/{key}"
        ) from exc


def upload_bytes(
    data: bytes,
    folder: str,
    filename: str | None = None,
    content_type: str = "image/jpeg",
) -> str:
    """Upload raw image bytes to S3 and return the object key."""
    client = _get_client()
    key = f"{folder}/{filename or uuid.uuid4()}.jpg"
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def get_presigned_url(key: str, expires_seconds: int = 3600) -> str:
    """Generate a pre-signed URL for temporary access to a stored image.

    Uses ``S3_PUBLIC_URL`` (browser-reachable) instead of ``S3_ENDPOINT_URL``
    (Docker-internal) so the returned URL works from the admin dashboard.
    """
    client = _get_presign_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
