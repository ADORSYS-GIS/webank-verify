"""Passive liveness detection with quality metrics using OpenCV."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import numpy as np


@dataclass
class FrameMetrics:
    face_quality: float = 0.0      # sharpness / blur score
    face_occlusion: float = 0.0    # % of face area covered / dark
    face_luminance: float = 0.0    # average brightness of face region
    face_detected: bool = False


@dataclass
class LivenessResult:
    liveness_score: float = 0.0
    face_quality: float = 0.0
    face_occlusion: float = 0.0
    face_luminance: float = 0.0
    frames_analyzed: int = 0
    passed: bool = False
    per_frame: list[FrameMetrics] = field(default_factory=list)

    LIVENESS_THRESHOLD: float = 60.0  # minimum score to pass


def _decode_frame(b64: str) -> np.ndarray:
    import cv2  # noqa: PLC0415

    data = base64.b64decode(b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode frame")
    return img


def _laplacian_variance(gray: np.ndarray) -> float:
    """Higher = sharper image. < 100 usually means blurry."""
    import cv2  # noqa: PLC0415

    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _detect_face_region(img: np.ndarray) -> np.ndarray | None:
    """Return the face ROI using Haar cascades (fast, no GPU needed)."""
    import cv2  # noqa: PLC0415

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = faces[0]
    return img[y:y + h, x:x + w]


def _lbp_texture_score(gray: np.ndarray) -> float:
    """
    Local Binary Pattern variance as an anti-spoofing signal.
    Real faces have higher texture variance than printed photos or screens.
    Returns score 0-100 (higher = more likely real).
    """
    h, w = gray.shape
    if h < 16 or w < 16:
        return 50.0

    scores = []
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            center = int(gray[i, j])
            neighbors = [
                int(gray[i - 1, j - 1]), int(gray[i - 1, j]), int(gray[i - 1, j + 1]),
                int(gray[i, j + 1]), int(gray[i + 1, j + 1]),
                int(gray[i + 1, j]), int(gray[i + 1, j - 1]), int(gray[i, j - 1]),
            ]
            code = sum((1 if n >= center else 0) << k for k, n in enumerate(neighbors))
            scores.append(code)

    variance = float(np.var(scores))
    # Normalize: typical real face variance 1000-5000
    normalized = min(100.0, variance / 50.0)
    return round(normalized, 2)


def _inter_frame_motion(frames: list[np.ndarray]) -> float:
    """
    Compute average motion between consecutive frames.
    Real faces show micro-movements; static photos show near-zero motion.
    Returns score 0-100.
    """
    import cv2  # noqa: PLC0415

    if len(frames) < 2:
        return 50.0

    motion_scores = []
    for i in range(1, len(frames)):
        prev = cv2.cvtColor(frames[i - 1], cv2.COLOR_BGR2GRAY).astype(float)
        curr = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY).astype(float)
        diff = np.abs(curr - prev)
        # Mean absolute difference — real faces: 2-15, static photo: < 1
        mad = float(np.mean(diff))
        motion_scores.append(min(100.0, mad * 8))

    return round(float(np.mean(motion_scores)), 2)


def _analyze_frame(img: np.ndarray) -> FrameMetrics:
    import cv2  # noqa: PLC0415

    metrics = FrameMetrics()
    face_roi = _detect_face_region(img)
    if face_roi is None:
        return metrics

    metrics.face_detected = True
    gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)

    # Face quality (sharpness) — normalize Laplacian variance to 0-100
    lap_var = _laplacian_variance(gray_face)
    metrics.face_quality = round(min(100.0, lap_var / 10.0), 2)

    # Luminance — mean brightness of face region
    metrics.face_luminance = round(float(np.mean(gray_face)) / 255.0 * 100.0, 2)

    # Occlusion — approximate: check if large dark region covers face
    dark_pixels = np.sum(gray_face < 50)
    total_pixels = gray_face.size
    metrics.face_occlusion = round(dark_pixels / total_pixels * 100.0, 2)

    return metrics


def analyze_frames(frames_b64: list[str]) -> LivenessResult:
    """
    Analyze a list of base64-encoded frames for passive liveness.
    Combines LBP texture, inter-frame motion, and per-frame quality metrics.
    """
    if not frames_b64:
        return LivenessResult()

    decoded = []
    for b64 in frames_b64:
        try:
            decoded.append(_decode_frame(b64))
        except ValueError:
            continue

    if not decoded:
        return LivenessResult()

    per_frame = [_analyze_frame(img) for img in decoded]
    detected_frames = [m for m in per_frame if m.face_detected]

    if not detected_frames:
        return LivenessResult(frames_analyzed=len(decoded), per_frame=per_frame)

    avg_quality = float(np.mean([m.face_quality for m in detected_frames]))
    avg_occlusion = float(np.mean([m.face_occlusion for m in detected_frames]))
    avg_luminance = float(np.mean([m.face_luminance for m in detected_frames]))

    # LBP texture on best (sharpest) frame
    best_frame_idx = max(range(len(per_frame)), key=lambda i: per_frame[i].face_quality if per_frame[i].face_detected else 0)
    best_img = decoded[best_frame_idx]
    import cv2  # noqa: PLC0415
    best_face = _detect_face_region(best_img)
    if best_face is not None:
        gray_best = cv2.cvtColor(best_face, cv2.COLOR_BGR2GRAY)
        texture_score = _lbp_texture_score(gray_best)
    else:
        texture_score = 50.0

    motion_score = _inter_frame_motion(decoded)

    # Weighted liveness score
    liveness = (
        texture_score * 0.40
        + motion_score * 0.35
        + avg_quality * 0.15
        + (100 - avg_occlusion) * 0.10
    )
    liveness = round(min(100.0, max(0.0, liveness)), 2)

    return LivenessResult(
        liveness_score=liveness,
        face_quality=round(avg_quality, 2),
        face_occlusion=round(avg_occlusion, 2),
        face_luminance=round(avg_luminance, 2),
        frames_analyzed=len(decoded),
        passed=liveness >= LivenessResult.LIVENESS_THRESHOLD,
        per_frame=per_frame,
    )
