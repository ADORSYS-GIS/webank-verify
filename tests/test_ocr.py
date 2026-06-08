"""Tests for OCR service — mocks easyocr to test field extraction logic."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.ocr_service import (
    DocumentFields,
    _compute_age,
    _parse_date,
    extract_from_cni,
)
from datetime import date


def test_parse_date_slash():
    result = _parse_date("15/06/1990")
    assert result == date(1990, 6, 15)


def test_parse_date_dash():
    result = _parse_date("15-06-1990")
    assert result == date(1990, 6, 15)


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None


def test_compute_age():
    dob = date(1990, 1, 1)
    age = _compute_age(dob)
    assert age >= 34  # adjust as time passes


@patch("app.services.ocr_service._get_reader")
@patch("app.services.ocr_service._decode_image")
def test_extract_cni_basic(mock_decode, mock_reader):
    mock_decode.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader.return_value = MagicMock(
        readtext=lambda *a, **kw: [
            (None, "NOM: MBIDA", 0.9),
            (None, "PRENOM: JEAN PAUL", 0.88),
            (None, "NÉ LE 15/06/1990", 0.85),
            (None, "À YAOUNDÉ", 0.80),
            (None, "N° 123456789", 0.92),
        ]
    )

    # Create a tiny 1x1 white JPEG in base64
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    fields = extract_from_cni(b64)

    assert fields.last_name == "Mbida"
    assert fields.first_name == "Jean Paul"
    assert fields.date_of_birth == "15/06/1990"
    assert fields.birth_place == "Yaoundé"
    assert fields.document_number == "123456789"
    assert fields.age is not None
    assert not fields.is_underage


@patch("app.services.ocr_service._get_reader")
@patch("app.services.ocr_service._decode_image")
def test_expired_document(mock_decode, mock_reader):
    mock_decode.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader.return_value = MagicMock(
        readtext=lambda *a, **kw: [
            (None, "EXPIRE LE 01/01/2010", 0.9),
        ]
    )

    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    fields = extract_from_cni(b64)
    assert fields.is_expired is True


@patch("app.services.ocr_service._get_reader")
@patch("app.services.ocr_service._decode_image")
def test_underage_detection(mock_decode, mock_reader):
    from datetime import date, timedelta
    underage_dob = (date.today() - timedelta(days=365 * 16)).strftime("%d/%m/%Y")
    mock_decode.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader.return_value = MagicMock(
        readtext=lambda *a, **kw: [
            (None, f"NÉ LE {underage_dob}", 0.9),
        ]
    )

    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    fields = extract_from_cni(b64)
    assert fields.is_underage is True
    assert fields.age is not None and fields.age < 18
