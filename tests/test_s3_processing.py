from unittest.mock import MagicMock

from app.api.liveness import _process_liveness
from app.services.document_service import process_document_images


def test_document_processing_fetches_s3_uris_and_records_keys(monkeypatch):
    image_uris = [
        "s3://webank-verify/kyc/user/front.jpg",
        "s3://webank-verify/kyc/user/back.jpg",
    ]
    fetch_bytes = MagicMock(side_effect=[b"front", b"back"])
    monkeypatch.setattr("app.services.document_service.storage_service.fetch_bytes", fetch_bytes)
    monkeypatch.setattr(
        "app.services.document_service.storage_service.parse_s3_uri",
        lambda uri: ("webank-verify", uri.removeprefix("s3://webank-verify/")),
    )
    monkeypatch.setattr("app.services.document_service.ocr_service.extract_from_cni", lambda *args: "fields")
    monkeypatch.setattr("app.services.document_service.face_service.extract_embedding", lambda image: [0.1])

    fields, embedding, keys = process_document_images(image_uris, "CNI", "national_id")

    assert fields == "fields"
    assert embedding == [0.1]
    assert keys == ["kyc/user/front.jpg", "kyc/user/back.jpg"]
    assert fetch_bytes.call_args_list[0].args == (image_uris[0],)
    assert fetch_bytes.call_args_list[1].args == (image_uris[1],)


def test_liveness_processing_fetches_s3_uris_and_records_keys(monkeypatch):
    frame_uris = ["s3://webank-verify/kyc/user/frame_0.jpg"]
    monkeypatch.setattr("app.api.liveness.storage_service.fetch_bytes", lambda uri: b"frame")
    monkeypatch.setattr(
        "app.api.liveness.storage_service.parse_s3_uri",
        lambda uri: ("webank-verify", "kyc/user/frame_0.jpg"),
    )
    analyze_frames = MagicMock(return_value="result")
    monkeypatch.setattr("app.api.liveness.liveness_service.analyze_frames", analyze_frames)

    result, keys, frames = _process_liveness(frame_uris)

    assert result == "result"
    assert keys == ["kyc/user/frame_0.jpg"]
    assert frames == [b"frame"]
    analyze_frames.assert_called_once_with([b"frame"])
