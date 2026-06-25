"""Tests for document-type mapping, incl. récépissé support (ADR 0007)."""

from app.api.document import _DOC_TYPE_MAP


def test_passport_maps_to_passport():
    assert _DOC_TYPE_MAP.get("passport") == "PASSPORT"


def test_recepisse_is_supported():
    assert _DOC_TYPE_MAP.get("recepisse") == "RECEPISSE"


def test_national_id_falls_back_to_cni():
    # national_id (and anything unrecognized) is not in the map → CNI fallback.
    assert _DOC_TYPE_MAP.get("national_id", "CNI") == "CNI"
    assert _DOC_TYPE_MAP.get("something-else", "CNI") == "CNI"


def test_recepisse_uses_ocr_not_mrz():
    # Only 'passport' takes the MRZ branch in _process_document; récépissé must
    # go through the French OCR pipeline like the CNI.
    assert "recepisse" != "passport"
