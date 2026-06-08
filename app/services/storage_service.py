"""S3-compatible storage for document images and liveness frames."""

from __future__ import annotations

import base64
import uuid
from datetime import timedelta

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
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
    return _client


def upload_image(b64_data: str, folder: str, filename: str | None = None) -> str:
    """Upload a base64 image to S3. Returns the S3 key."""
    client = _get_client()
    key = f"{folder}/{filename or uuid.uuid4()}.jpg"
    data = base64.b64decode(b64_data)
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType="image/jpeg",
    )
    return key


def get_presigned_url(key: str, expires_seconds: int = 3600) -> str:
    """Generate a pre-signed URL for temporary access to a stored image."""
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
