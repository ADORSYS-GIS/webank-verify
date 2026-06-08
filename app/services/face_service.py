"""Face matching using deepface ArcFace model + duplicate detection."""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import dataclass

import numpy as np

SIMILARITY_THRESHOLD = 0.68  # ArcFace cosine distance threshold


@dataclass
class FaceMatchResult:
    similarity: float  # 0.0 – 1.0
    passed: bool
    distance: float
    model: str = "ArcFace"
    threshold_used: float = SIMILARITY_THRESHOLD
    face_found_in_id: bool = True
    face_found_in_selfie: bool = True


def _b64_to_temp_file(b64: str) -> str:
    """Write base64 image to a temp file and return path (deepface needs file paths)."""
    data = base64.b64decode(b64)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(data)
        return f.name


def _b64_to_numpy(b64: str) -> np.ndarray:
    import cv2  # noqa: PLC0415

    data = base64.b64decode(b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def extract_embedding(img_b64: str) -> list[float] | None:
    """Extract ArcFace embedding from an image. Returns None if no face detected."""
    try:
        from deepface import DeepFace  # noqa: PLC0415

        path = _b64_to_temp_file(img_b64)
        result = DeepFace.represent(img_path=path, model_name="ArcFace", enforce_detection=True)
        if result:
            return result[0]["embedding"]
    except Exception:
        return None
    return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def compare_faces(id_img_b64: str, selfie_b64: str) -> FaceMatchResult:
    """Compare face from ID document with selfie. Returns similarity and pass/fail."""
    try:
        from deepface import DeepFace  # noqa: PLC0415

        id_path = _b64_to_temp_file(id_img_b64)
        selfie_path = _b64_to_temp_file(selfie_b64)

        result = DeepFace.verify(
            img1_path=id_path,
            img2_path=selfie_path,
            model_name="ArcFace",
            distance_metric="cosine",
            enforce_detection=False,
        )
        distance = result.get("distance", 1.0)
        # Convert cosine distance (0=identical, 1=opposite) to similarity %
        similarity = max(0.0, 1.0 - distance)
        passed = distance <= SIMILARITY_THRESHOLD

        return FaceMatchResult(
            similarity=round(similarity * 100, 2),
            passed=passed,
            distance=round(distance, 4),
        )
    except Exception as exc:
        # Face not detected in one of the images
        no_face_in_id = "id" in str(exc).lower() or "img1" in str(exc).lower()
        return FaceMatchResult(
            similarity=0.0,
            passed=False,
            distance=1.0,
            face_found_in_id=not no_face_in_id,
            face_found_in_selfie=not (not no_face_in_id),
        )


def check_duplicate(embedding: list[float], existing_embeddings: list[tuple[str, list[float]]]) -> list[str]:
    """
    Check if this embedding matches any existing approved user.
    Returns list of user_ids that are duplicates (above threshold).
    """
    duplicates = []
    for user_id, stored_emb in existing_embeddings:
        sim = _cosine_similarity(embedding, stored_emb)
        if sim >= 1.0 - SIMILARITY_THRESHOLD:
            duplicates.append(user_id)
    return duplicates
