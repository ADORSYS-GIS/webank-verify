"""Face matching using deepface ArcFace model + duplicate detection."""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SIMILARITY_THRESHOLD = 0.68  # ArcFace cosine distance threshold

# Lazily imported, but exposed at module level so callers don't re-import on
# every call and tests can patch it.
DeepFace = None


def _load_deepface():
    global DeepFace
    if DeepFace is None:
        from deepface import DeepFace as _DF  # noqa: PLC0415

        DeepFace = _DF
    return DeepFace


@dataclass
class FaceMatchResult:
    similarity: float  # 0.0 – 100.0 (percent)
    passed: bool
    distance: float
    model: str = "ArcFace"
    threshold_used: float = SIMILARITY_THRESHOLD
    face_found_in_id: bool = True
    face_found_in_selfie: bool = True


def _bytes_to_temp_file(data: bytes) -> str:
    """Write image bytes to a temp file and return path (deepface needs file paths)."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(data)
        f.flush()
        return f.name


def _safe_unlink(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _bytes_to_numpy(data: bytes) -> np.ndarray:
    import cv2  # noqa: PLC0415

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def extract_embedding(image_bytes: bytes) -> list[float] | None:
    """Extract ArcFace embedding from an image. Returns None if no face detected."""
    path = None
    try:
        df = _load_deepface()
        path = _bytes_to_temp_file(image_bytes)
        result = df.represent(img_path=path, model_name="ArcFace", enforce_detection=True)
        if result:
            return result[0]["embedding"]
    except Exception:
        return None
    finally:
        _safe_unlink(path)
    return None


def warm_model(image_bytes: bytes) -> None:
    """Load ArcFace and run one detection-tolerant dummy representation."""
    path = None
    try:
        df = _load_deepface()
        path = _bytes_to_temp_file(image_bytes)
        df.represent(img_path=path, model_name="ArcFace", enforce_detection=False)
    finally:
        _safe_unlink(path)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def compare_faces(id_image_bytes: bytes, selfie_image_bytes: bytes) -> FaceMatchResult:
    """Compare face from ID document with selfie. Returns similarity and pass/fail."""
    id_path = None
    selfie_path = None
    try:
        df = _load_deepface()
        id_path = _bytes_to_temp_file(id_image_bytes)
        selfie_path = _bytes_to_temp_file(selfie_image_bytes)

        result = df.verify(
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
    except Exception:
        # Comparison failed (e.g. face not detected) — can't confirm either face.
        return FaceMatchResult(
            similarity=0.0,
            passed=False,
            distance=1.0,
            face_found_in_id=False,
            face_found_in_selfie=False,
        )
    finally:
        _safe_unlink(id_path)
        _safe_unlink(selfie_path)


def match_against_embedding(
    selfie_image_bytes: bytes, stored_embedding: list[float] | None
) -> FaceMatchResult | None:
    """Compare a selfie against a previously stored face embedding.

    Returns None if no face is detected in the selfie or there is no stored
    embedding to compare against.
    """
    if not stored_embedding:
        return None
    selfie_emb = extract_embedding(selfie_image_bytes)
    if not selfie_emb:
        return FaceMatchResult(
            similarity=0.0,
            passed=False,
            distance=1.0,
            face_found_in_selfie=False,
        )
    cos = _cosine_similarity(selfie_emb, stored_embedding)  # -1..1
    distance = 1.0 - cos
    similarity = max(0.0, cos) * 100
    return FaceMatchResult(
        similarity=round(similarity, 2),
        passed=distance <= SIMILARITY_THRESHOLD,
        distance=round(distance, 4),
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


def match_or_mint_person_id(
    embedding: list[float],
    existing_people: list[tuple[str, list[float]]],
) -> tuple[str, bool]:
    """Resolve a stable biometric ``person_id`` for a face embedding (ADR 0005).

    Compares ``embedding`` against the representative embedding of every known
    person (``existing_people`` = list of ``(person_id, embedding)``) and returns
    the ``person_id`` of the closest match above the ArcFace threshold — i.e. the
    same real person reuses the same key across accounts and document types.
    When nothing matches, a fresh ``person_id`` is minted.

    Returns ``(person_id, matched)`` where ``matched`` is True when an existing
    person was reused. The caller is responsible for never calling this without a
    real face embedding (no face → no person_id → fail closed).
    """
    best_pid: str | None = None
    best_sim = -1.0
    for person_id, stored_emb in existing_people:
        sim = _cosine_similarity(embedding, stored_emb)
        if sim >= 1.0 - SIMILARITY_THRESHOLD and sim > best_sim:
            best_sim = sim
            best_pid = person_id
    if best_pid is not None:
        return best_pid, True
    return str(uuid.uuid4()), False
