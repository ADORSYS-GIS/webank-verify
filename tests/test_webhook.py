"""Tests for webhook HMAC signing — the signature must cover the exact bytes sent."""

import hashlib
import hmac

from app.services import webhook_service


def test_signed_body_matches_transmitted_body():
    envelope = {
        "id": "abc",
        "event": "kyc.level3.approved",
        "timestamp": "2026-06-08T00:00:00+00:00",
        "data": {"user_id": "u1", "check_id": "c1"},
    }
    body = webhook_service._serialize(envelope)
    signature = webhook_service._sign_body(body, "shhh")

    # A receiver verifies the HMAC over the raw request body it received.
    expected = "sha256=" + hmac.new(b"shhh", body.encode(), hashlib.sha256).hexdigest()
    assert signature == expected


def test_serialize_is_deterministic():
    a = webhook_service._serialize({"b": 1, "a": 2})
    b = webhook_service._serialize({"a": 2, "b": 1})
    assert a == b  # sorted keys → stable signature regardless of dict order
