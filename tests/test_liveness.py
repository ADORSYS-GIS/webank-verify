"""Tests for liveness detection service."""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from app.services.liveness_service import (
    LivenessResult,
    _inter_frame_motion,
    _lbp_texture_score,
    analyze_frames,
)


def _make_frame_b64(width: int = 200, height: int = 200, color: tuple = (128, 128, 128)) -> str:
    """Create a synthetic JPEG frame in base64."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def test_empty_frames_returns_zero_score():
    result = analyze_frames([])
    assert result.liveness_score == 0.0
    assert result.frames_analyzed == 0


def test_single_frame_analyzed():
    frame = _make_frame_b64()
    result = analyze_frames([frame])
    assert result.frames_analyzed == 1
    assert 0.0 <= result.liveness_score <= 100.0


def test_multiple_frames_analyzed():
    frames = [_make_frame_b64(color=(c, c, c)) for c in (100, 110, 120)]
    result = analyze_frames(frames)
    assert result.frames_analyzed == 3


def test_inter_frame_motion_identical_frames():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    score = _inter_frame_motion([frame, frame, frame])
    assert score < 10.0  # identical frames → near-zero motion


def test_inter_frame_motion_different_frames():
    frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
    frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 200
    score = _inter_frame_motion([frame1, frame2])
    assert score > 0.0


def test_lbp_texture_uniform_image():
    gray = np.ones((50, 50), dtype=np.uint8) * 128
    score = _lbp_texture_score(gray)
    assert 0.0 <= score <= 100.0


def test_liveness_result_threshold():
    result = LivenessResult(liveness_score=70.0)
    result.passed = result.liveness_score >= LivenessResult.LIVENESS_THRESHOLD
    assert result.passed is True

    result2 = LivenessResult(liveness_score=40.0)
    result2.passed = result2.liveness_score >= LivenessResult.LIVENESS_THRESHOLD
    assert result2.passed is False
