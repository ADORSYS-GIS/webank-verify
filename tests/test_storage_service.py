from unittest.mock import MagicMock

import pytest

from app.services import storage_service


def test_fetch_bytes_rejects_non_s3_uri():
    with pytest.raises(ValueError, match="s3://"):
        storage_service.fetch_bytes("https://webank-verify/kyc/user/front.jpg")


def test_fetch_bytes_rejects_cross_bucket_uri():
    with pytest.raises(ValueError, match="does not match"):
        storage_service.fetch_bytes("s3://another-bucket/kyc/user/front.jpg")


def test_fetch_bytes_reads_validated_s3_object(monkeypatch):
    body = MagicMock()
    body.read.return_value = b"image-bytes"
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    monkeypatch.setattr(storage_service, "_get_client", lambda: client)

    assert storage_service.fetch_bytes("s3://webank-verify/kyc/user/front.jpg") == b"image-bytes"
    client.get_object.assert_called_once_with(Bucket="webank-verify", Key="kyc/user/front.jpg")
