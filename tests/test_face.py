"""Tests for face matching service."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.face_service import (
    SIMILARITY_THRESHOLD,
    FaceMatchResult,
    _cosine_similarity,
    check_duplicate,
)


def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_zero_vector():
    result = _cosine_similarity([0.0, 0.0], [1.0, 0.0])
    assert result == 0.0


def test_check_duplicate_no_match():
    embedding = [1.0, 0.0, 0.0]
    existing = [("user-1", [0.0, 1.0, 0.0])]
    duplicates = check_duplicate(embedding, existing)
    assert duplicates == []


def test_check_duplicate_finds_match():
    embedding = [1.0, 0.0, 0.0]
    existing = [("user-1", [1.0, 0.0, 0.0])]
    duplicates = check_duplicate(embedding, existing)
    assert "user-1" in duplicates


def test_face_match_result_structure():
    result = FaceMatchResult(similarity=90.0, passed=True, distance=0.1)
    assert result.similarity == 90.0
    assert result.passed is True
    assert result.model == "ArcFace"
    assert result.threshold_used == SIMILARITY_THRESHOLD


@patch("app.services.face_service.DeepFace")
def test_compare_faces_pass(mock_deepface):
    """Test that low distance → passed=True."""
    mock_deepface.verify.return_value = {"distance": 0.30, "verified": True}
    with patch("app.services.face_service._b64_to_temp_file", return_value="/tmp/fake.jpg"):
        from app.services.face_service import compare_faces
        result = compare_faces("fake_id_b64", "fake_selfie_b64")
        assert result.passed is True
        assert result.similarity > 0


@patch("app.services.face_service.DeepFace")
def test_compare_faces_fail(mock_deepface):
    """Test that high distance → passed=False."""
    mock_deepface.verify.return_value = {"distance": 0.90, "verified": False}
    with patch("app.services.face_service._b64_to_temp_file", return_value="/tmp/fake.jpg"):
        from app.services.face_service import compare_faces
        result = compare_faces("fake_id_b64", "fake_selfie_b64")
        assert result.passed is False
