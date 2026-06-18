"""OCR extraction for Cameroonian CNI and Passport using easyocr (French)."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np

_reader = None  # lazy-loaded


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr  # noqa: PLC0415

        _reader = easyocr.Reader(["fr"], gpu=False)
    return _reader


@dataclass
class DocumentFields:
    type: str = "unknown"
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    birth_place: str | None = None
    document_number: str | None = None
    expiry_date: str | None = None
    is_expired: bool = False
    age: int | None = None
    is_underage: bool = False
    confidence: float = 0.0
    raw_text: list[str] = field(default_factory=list)


# Regex patterns for Cameroonian CNI fields.
# Name/place capture classes use a literal space (not \s) so a match cannot
# bleed across newlines into the following field. The birth-place anchor is the
# accented "À"/"à" only — a bare "A" matches far too much OCR noise.
_PATTERNS = {
    "last_name": re.compile(r"(?:NOM|Nom)\s*[:\-]?[ \t]*([A-ZÉÈÊËÀÂÙÛÜÏÎ \-]+)", re.IGNORECASE),
    "first_name": re.compile(r"(?:PRENOM[S]?|Prénom[s]?)\s*[:\-]?[ \t]*([A-ZÉÈÊËÀÂÙÛÜÏÎ \-]+)", re.IGNORECASE),
    "dob": re.compile(r"(?:NÉ[E]?\s+LE|Né[e]?\s+le)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})"),
    "birth_place": re.compile(r"(?:À|à)\s*[:\-]?[ \t]*([A-ZÉÈÊËÀÂÙÛÜÏÎ \-]+)", re.IGNORECASE),
    "doc_number": re.compile(r"(?:N[°º]|No\.?)\s*[:\-]?\s*([0-9]{6,12})"),
    "expiry": re.compile(r"(?:EXPIRE[S]?\s+LE|Expire\s+le|VALABLE\s+JUSQU|Date\s+d.expiration)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", re.IGNORECASE),
}

_DATE_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"]


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _compute_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _decode_image(b64: str) -> np.ndarray:
    import cv2  # noqa: PLC0415

    data = base64.b64decode(b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def extract_from_cni(front_b64: str, back_b64: str | None = None, doc_type: str = "national_id") -> DocumentFields:
    """Run OCR on CNI or Passport image(s) and extract structured fields."""
    reader = _get_reader()
    img = _decode_image(front_b64)

    results = reader.readtext(img, detail=1, paragraph=False)
    lines = [text for (_, text, conf) in results if conf > 0.3]
    avg_conf = sum(conf for (_, _, conf) in results) / max(len(results), 1)

    full_text = "\n".join(lines)
    fields = DocumentFields(type=doc_type, raw_text=lines, confidence=round(avg_conf, 3))

    # Extract last name
    if m := _PATTERNS["last_name"].search(full_text):
        fields.last_name = m.group(1).strip().title()

    # Extract first name
    if m := _PATTERNS["first_name"].search(full_text):
        fields.first_name = m.group(1).strip().title()

    # Extract date of birth
    if m := _PATTERNS["dob"].search(full_text):
        raw_dob = m.group(1)
        fields.date_of_birth = raw_dob
        parsed = _parse_date(raw_dob)
        if parsed:
            fields.age = _compute_age(parsed)
            fields.is_underage = fields.age < 18

    # Extract birth place
    if m := _PATTERNS["birth_place"].search(full_text):
        candidate = m.group(1).strip().title()
        # Avoid matching noise (single chars, numbers)
        if len(candidate) > 2 and not candidate[0].isdigit():
            fields.birth_place = candidate

    # Extract document number
    if m := _PATTERNS["doc_number"].search(full_text):
        fields.document_number = m.group(1).strip()

    # Extract expiry date
    if m := _PATTERNS["expiry"].search(full_text):
        raw_exp = m.group(1)
        fields.expiry_date = raw_exp
        parsed_exp = _parse_date(raw_exp)
        if parsed_exp:
            fields.is_expired = parsed_exp < date.today()

    # Also run OCR on back if provided (may contain document number)
    if back_b64 and not fields.document_number:
        back_img = _decode_image(back_b64)
        back_results = reader.readtext(back_img, detail=1, paragraph=False)
        back_lines = [text for (_, text, conf) in back_results if conf > 0.3]
        back_text = "\n".join(back_lines)
        if m := _PATTERNS["doc_number"].search(back_text):
            fields.document_number = m.group(1).strip()

    return fields
