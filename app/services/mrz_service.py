"""MRZ (Machine Readable Zone) parser for Cameroonian passports."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import numpy as np


_reader = None  # lazy-loaded, cached across calls


def _get_reader():
    global _reader
    if _reader is None:
        from easyocr import Reader  # noqa: PLC0415

        _reader = Reader(["en"], gpu=False)
    return _reader


@dataclass
class MRZFields:
    document_type: str | None = None
    country: str | None = None
    last_name: str | None = None
    first_name: str | None = None
    document_number: str | None = None
    nationality: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    expiry_date: str | None = None
    personal_number: str | None = None
    is_valid_checksum: bool = False
    raw_mrz: str | None = None


def _mrz_checksum(data: str) -> int:
    weights = [7, 3, 1]
    total = 0
    for i, ch in enumerate(data):
        if ch.isdigit():
            val = int(ch)
        elif ch.isalpha():
            val = ord(ch.upper()) - 55
        elif ch == "<":
            val = 0
        else:
            val = 0
        total += val * weights[i % 3]
    return total % 10


def _decode_date(raw: str) -> str | None:
    """Convert YYMMDD → DD/MM/YYYY (assume 1900s if YY > 30 else 2000s)."""
    if len(raw) != 6 or not raw.isdigit():
        return None
    yy, mm, dd = int(raw[:2]), raw[2:4], raw[4:6]
    year = 1900 + yy if yy > 30 else 2000 + yy
    return f"{dd}/{mm}/{year}"


def _extract_mrz_from_image(img_b64: str) -> str | None:
    """Try to detect and extract MRZ text from a passport image using OpenCV + easyocr."""
    import cv2  # noqa: PLC0415

    data = base64.b64decode(img_b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    # MRZ is in the bottom ~20% of passport
    h, w = img.shape[:2]
    roi = img[int(h * 0.75):, :]

    # Convert to grayscale + threshold for high-contrast MRZ font
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Use easyocr on the ROI
    try:
        reader = _get_reader()
        results = reader.readtext(thresh, detail=0, paragraph=False)
        # MRZ lines are 44 chars each (TD3 passport), uppercase + digits + <
        mrz_pattern = re.compile(r"^[A-Z0-9<]{30,44}$")
        mrz_lines = [line.replace(" ", "") for line in results if mrz_pattern.match(line.replace(" ", ""))]
        if len(mrz_lines) >= 2:
            return "\n".join(mrz_lines[:2])
    except Exception:
        pass
    return None


def _parse_td3(line1: str, line2: str) -> MRZFields:
    """Parse TD3 (passport) MRZ — 2 lines of 44 chars."""
    fields = MRZFields(raw_mrz=f"{line1}\n{line2}")

    # Line 1: P<CMNOMN<<PRENOM<<<<<<<<<<<<<<<<<<<<<<<<<<<
    if len(line1) >= 44:
        fields.document_type = line1[0]
        fields.country = line1[2:5].replace("<", "")
        name_part = line1[5:44]
        parts = name_part.split("<<")
        if parts:
            fields.last_name = parts[0].replace("<", " ").strip().title()
        if len(parts) > 1:
            fields.first_name = parts[1].replace("<", " ").strip().title()

    # Line 2: DOCNUM<CHNATIONALITY DOBYYYY SEX EXPYYYY PERSONAL#CHECKSUM
    if len(line2) >= 44:
        fields.document_number = line2[0:9].replace("<", "")
        # checksum line2[9]
        fields.nationality = line2[10:13].replace("<", "")
        fields.date_of_birth = _decode_date(line2[13:19])
        fields.sex = line2[20] if line2[20] in ("M", "F") else None
        fields.expiry_date = _decode_date(line2[21:27])
        fields.personal_number = line2[28:42].replace("<", "")

        # Validate overall checksum (line2[43])
        composite = line2[0:10] + line2[13:20] + line2[21:43]
        try:
            expected = int(line2[43])
            fields.is_valid_checksum = _mrz_checksum(composite) == expected
        except (ValueError, IndexError):
            fields.is_valid_checksum = False

    return fields


def extract_from_passport(img_b64: str) -> MRZFields | None:
    """Extract MRZ fields from a passport image. Returns None if no MRZ detected."""
    raw_mrz = _extract_mrz_from_image(img_b64)
    if raw_mrz is None:
        return None

    lines = [l.strip() for l in raw_mrz.split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    return _parse_td3(lines[0], lines[1])
