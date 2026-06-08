"""Weighted fraud risk scorer and warnings engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.face_service import FaceMatchResult
from app.services.ip_service import IPAnalysis
from app.services.liveness_service import LivenessResult
from app.services.ocr_service import DocumentFields


@dataclass
class Warning:
    code: str
    message: str
    severity: str  # "info" | "warning" | "critical"


@dataclass
class RiskResult:
    overall_score: float = 0.0  # 0 (no risk) → 100 (maximum risk)
    decision: str = "manual_review"  # "approved" | "rejected" | "manual_review"
    warnings: list[Warning] = field(default_factory=list)
    requires_manual_review: bool = True

    # Component scores (higher = worse in this context means lower verification quality)
    liveness_component: float = 0.0
    face_component: float = 0.0
    document_component: float = 0.0
    ip_component: float = 0.0


# ── Thresholds ────────────────────────────────────────────────────────────────
AUTO_APPROVE_THRESHOLD = 25   # overall risk ≤ this → auto-approve
AUTO_REJECT_THRESHOLD = 75    # overall risk ≥ this → auto-reject (or flag for review)
FACE_SIMILARITY_MIN = 70.0    # % minimum to pass face match
LIVENESS_MIN = 60.0           # minimum liveness score to pass


def _invert(score: float, max_val: float = 100.0) -> float:
    """Convert a quality score (higher=better) to a risk contribution (higher=worse)."""
    return max(0.0, max_val - score)


def compute_risk(
    liveness: LivenessResult | None,
    face_match: FaceMatchResult | None,
    document: DocumentFields | None,
    ip: IPAnalysis | None,
    duplicate_user_ids: list[str] | None = None,
) -> RiskResult:
    result = RiskResult()
    warnings: list[Warning] = []

    # ── Document component (weight 0.20) ──────────────────────────────────────
    doc_risk = 0.0
    if document:
        doc_confidence = document.confidence * 100
        doc_risk = _invert(doc_confidence)

        if document.is_expired:
            doc_risk = min(100.0, doc_risk + 40)
            warnings.append(Warning("EXPIRED_DOCUMENT", "Document has expired", "critical"))

        if document.is_underage:
            doc_risk = min(100.0, doc_risk + 30)
            warnings.append(Warning("UNDERAGE", f"User is under 18 (age: {document.age})", "critical"))

        if not document.document_number:
            doc_risk = min(100.0, doc_risk + 20)
            warnings.append(Warning("MISSING_DOC_NUMBER", "Document number could not be extracted", "warning"))

        if document.confidence < 0.4:
            warnings.append(Warning("LOW_OCR_CONFIDENCE", "Low OCR confidence — image may be blurry", "warning"))
    else:
        doc_risk = 100.0
        warnings.append(Warning("NO_DOCUMENT", "No document fields extracted", "critical"))

    result.document_component = round(doc_risk, 2)

    # ── Liveness component (weight 0.35) ──────────────────────────────────────
    liv_risk = 0.0
    if liveness and liveness.frames_analyzed > 0:
        liv_risk = _invert(liveness.liveness_score)
        if not liveness.passed:
            warnings.append(Warning("LOW_LIVENESS", f"Liveness score {liveness.liveness_score:.1f}% below threshold", "critical"))
        if liveness.face_occlusion > 30:
            warnings.append(Warning("FACE_OCCLUSION", f"Face occlusion {liveness.face_occlusion:.1f}% — face may be partially covered", "warning"))
        if liveness.face_luminance < 20:
            warnings.append(Warning("LOW_LUMINANCE", "Face too dark — poor lighting conditions", "warning"))
        if liveness.face_quality < 30:
            warnings.append(Warning("BLURRY_IMAGE", "Image quality too low", "warning"))
    else:
        liv_risk = 50.0  # no liveness submitted yet
    result.liveness_component = round(liv_risk, 2)

    # ── Face match component (weight 0.35) ────────────────────────────────────
    face_risk = 0.0
    if face_match:
        face_risk = _invert(face_match.similarity)
        if not face_match.passed:
            warnings.append(Warning("FACE_MISMATCH", f"Face similarity {face_match.similarity:.1f}% below threshold", "critical"))
        if not face_match.face_found_in_id:
            warnings.append(Warning("NO_FACE_IN_DOCUMENT", "No face detected in the ID document", "warning"))
        if not face_match.face_found_in_selfie:
            warnings.append(Warning("NO_FACE_IN_SELFIE", "No face detected in the selfie", "warning"))
    else:
        face_risk = 50.0
    result.face_component = round(face_risk, 2)

    # ── IP component (weight 0.10) ────────────────────────────────────────────
    ip_risk = 0.0
    if ip:
        ip_risk = ip.risk_score
        for flag in ip.risk_flags:
            if flag == "VPN_DETECTED":
                warnings.append(Warning("VPN_DETECTED", "Request originated from a VPN or hosting provider", "warning"))
            elif flag == "PROXY_DETECTED":
                warnings.append(Warning("PROXY_DETECTED", "Request originated from a proxy", "warning"))
            elif flag.startswith("NON_CAMEROON_IP"):
                country = flag.split(":")[-1]
                warnings.append(Warning("NON_CAMEROON_IP", f"IP address located in {country}, not Cameroon", "info"))
    result.ip_component = round(ip_risk, 2)

    # ── Duplicate detection ───────────────────────────────────────────────────
    if duplicate_user_ids:
        warnings.append(Warning(
            "DUPLICATE_FACE",
            f"Face matches existing approved user(s): {', '.join(duplicate_user_ids[:3])}",
            "critical",
        ))

    # ── Weighted aggregate ────────────────────────────────────────────────────
    overall = (
        result.liveness_component * 0.35
        + result.face_component * 0.35
        + result.document_component * 0.20
        + result.ip_component * 0.10
    )
    result.overall_score = round(min(100.0, overall), 2)
    result.warnings = warnings

    # ── Auto-decision ─────────────────────────────────────────────────────────
    has_critical = any(w.severity == "critical" for w in warnings)
    if result.overall_score <= AUTO_APPROVE_THRESHOLD and not has_critical:
        result.decision = "approved"
        result.requires_manual_review = False
    elif result.overall_score >= AUTO_REJECT_THRESHOLD or (has_critical and result.overall_score > 50):
        result.decision = "rejected"
        result.requires_manual_review = False
    else:
        result.decision = "manual_review"
        result.requires_manual_review = True

    return result
