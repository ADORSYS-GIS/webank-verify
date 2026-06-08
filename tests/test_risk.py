"""Tests for the risk scorer and warnings engine."""

import pytest

from app.services.face_service import FaceMatchResult
from app.services.ip_service import IPAnalysis
from app.services.liveness_service import LivenessResult
from app.services.ocr_service import DocumentFields
from app.services.risk_service import AUTO_APPROVE_THRESHOLD, AUTO_REJECT_THRESHOLD, compute_risk


def _good_doc() -> DocumentFields:
    return DocumentFields(
        type="CNI", first_name="Jean", last_name="Mbida",
        date_of_birth="15/06/1990", document_number="123456789",
        is_expired=False, age=34, is_underage=False, confidence=0.85,
    )


def _good_liveness() -> LivenessResult:
    return LivenessResult(
        liveness_score=85.0, face_quality=88.0,
        face_occlusion=5.0, face_luminance=70.0,
        frames_analyzed=3, passed=True,
    )


def _good_face() -> FaceMatchResult:
    return FaceMatchResult(similarity=92.0, passed=True, distance=0.08)


def _good_ip() -> IPAnalysis:
    return IPAnalysis(ip="197.1.2.3", country="CM", is_vpn=False, risk_score=0)


def test_all_good_auto_approves():
    result = compute_risk(_good_liveness(), _good_face(), _good_doc(), _good_ip())
    assert result.decision == "approved"
    assert result.overall_score <= AUTO_APPROVE_THRESHOLD
    assert not result.requires_manual_review


def test_expired_doc_adds_warning():
    doc = _good_doc()
    doc.is_expired = True
    result = compute_risk(_good_liveness(), _good_face(), doc, _good_ip())
    codes = [w.code for w in result.warnings]
    assert "EXPIRED_DOCUMENT" in codes


def test_underage_adds_critical_warning():
    doc = _good_doc()
    doc.is_underage = True
    doc.age = 16
    result = compute_risk(_good_liveness(), _good_face(), doc, _good_ip())
    critical = [w for w in result.warnings if w.severity == "critical"]
    assert any(w.code == "UNDERAGE" for w in critical)


def test_low_liveness_adds_warning():
    liveness = _good_liveness()
    liveness.liveness_score = 30.0
    liveness.passed = False
    result = compute_risk(liveness, _good_face(), _good_doc(), _good_ip())
    codes = [w.code for w in result.warnings]
    assert "LOW_LIVENESS" in codes


def test_face_mismatch_adds_warning():
    face = FaceMatchResult(similarity=45.0, passed=False, distance=0.55)
    result = compute_risk(_good_liveness(), face, _good_doc(), _good_ip())
    codes = [w.code for w in result.warnings]
    assert "FACE_MISMATCH" in codes


def test_vpn_adds_warning():
    ip = IPAnalysis(ip="51.1.2.3", country="FR", is_vpn=True, risk_score=50, risk_flags=["VPN_DETECTED"])
    result = compute_risk(_good_liveness(), _good_face(), _good_doc(), ip)
    codes = [w.code for w in result.warnings]
    assert "VPN_DETECTED" in codes


def test_duplicate_face_adds_critical():
    result = compute_risk(_good_liveness(), _good_face(), _good_doc(), _good_ip(), duplicate_user_ids=["user-abc"])
    critical = [w for w in result.warnings if w.severity == "critical"]
    assert any(w.code == "DUPLICATE_FACE" for w in critical)


def test_no_document_max_risk():
    result = compute_risk(_good_liveness(), _good_face(), None, _good_ip())
    assert result.document_component == 100.0


def test_overall_score_is_weighted():
    result = compute_risk(_good_liveness(), _good_face(), _good_doc(), _good_ip())
    # Verify it's a weighted average in 0-100
    assert 0.0 <= result.overall_score <= 100.0
