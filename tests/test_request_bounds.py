import pytest
from pydantic import ValidationError

from app.models.request import DocumentSubmitRequest, LivenessVerifyRequest


def test_document_submission_rejects_more_than_two_images():
    with pytest.raises(ValidationError):
        DocumentSubmitRequest(
            user_id="user123",
            image_uris=["s3://webank-verify/a", "s3://webank-verify/b", "s3://webank-verify/c"],
            doc_type="national_id",
        )


def test_liveness_submission_rejects_more_than_ten_frames():
    with pytest.raises(ValidationError):
        LivenessVerifyRequest(
            user_id="user123",
            frame_uris=[f"s3://webank-verify/frame-{index}" for index in range(11)],
        )
