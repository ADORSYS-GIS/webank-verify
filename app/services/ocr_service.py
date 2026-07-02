"""OCR extraction for Cameroonian CNI and Passport using easyocr (French/English).

The Cameroon CNI is bilingual (French/English). Labels appear as:
  NOM / SURNAME
  PRENOMS / GIVEN NAMES
  DATE DE NAISSANCE / DATE OF BIRTH
  LIEU DE NAISSANCE / PLACE OF BIRTH
  SEXE / SEX
  TAILLE / HEIGHT
  PROFESSION / OCCUPATION
  SIGNATURE

Back side:
  PERE / FATHER
  MERE / MOTHER
  DATE DE DELIVRANCE / DATE OF ISSUE
  DATE D'EXPIRATION / DATE OF EXPIRY
  IDENTIFIANT UNIQUE / UNIQUE IDENTIFIER

easyocr often garbles the bilingual labels (e.g. ``NOM / SURNAME`` → ``mMWNAURNAME``)
while reading the values cleanly. We therefore:
  1. Keep ALL OCR lines (no confidence filter) so garbled labels survive.
  2. Use fuzzy keyword matching instead of strict regex for label detection.
  3. Preprocess images (grayscale, CLAHE, upscale, denoise) to improve OCR.
  4. Fall back to value-based extraction (dates, names, numbers) when labels
     are too garbled to match.
"""

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

        _reader = easyocr.Reader(["fr", "en"], gpu=False)
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
    issue_date: str | None = None
    is_expired: bool = False
    age: int | None = None
    is_underage: bool = False
    sex: str | None = None
    height: str | None = None
    profession: str | None = None
    father: str | None = None
    mother: str | None = None
    confidence: float = 0.0
    raw_text: list[str] = field(default_factory=list)
    raw_text_back: list[str] = field(default_factory=list)


# ── Date / number helpers ─────────────────────────────────────────────────────

# Handle single or double separators between date parts, e.g. "23,.09.2004"
_DATE_RE = re.compile(r"(\d{1,2}[/\-.,]{1,2}\d{1,2}[/\-.,]{1,2}\d{2,4})")
_DOC_NUMBER_RE = re.compile(r"([0-9]{6,20})")
_HEIGHT_RE = re.compile(r"(\d{1,3}[.,]?\d{0,2})")
_DATE_FMTS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%d,%m/%Y", "%d,%m.%Y", "%d.%m,%Y",
    "%d,%m,%y",
]


def _parse_date(raw: str) -> date | None:
    # Normalise double-separator artifacts like "23,.09.2004" → "23.09.2004"
    raw = re.sub(r"[,\.]{2,}", ".", raw.strip())
    raw = raw.replace(",", ".")
    for fmt in _DATE_FMTS:
        try:
            d = datetime.strptime(raw, fmt).date()
            # Sanity: reject years that are clearly OCR misreads
            # (valid range 1920–2050 for Cameroon CNI dates)
            if not (1920 <= d.year <= 2050):
                continue
            return d
        except ValueError:
            continue
    return None


def _compute_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ── Image preprocessing ──────────────────────────────────────────────────────

def _decode_image(b64: str) -> np.ndarray:
    import cv2  # noqa: PLC0415

    data = base64.b64decode(b64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def _preprocess_image(img: np.ndarray) -> np.ndarray:
    """Enhance image quality for OCR: grayscale, CLAHE, upscale, denoise."""
    import cv2  # noqa: PLC0415

    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # Upscale if image is small (easyocr works better with larger images)
    h, w = gray.shape
    if max(h, w) < 1200:
        scale = 1200 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Denoise (positional args for OpenCV 4.x and 5.x compatibility)
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
    return denoised


# ── Fuzzy label matching ──────────────────────────────────────────────────────

def _normalize_text(s: str) -> str:
    """Normalize text for fuzzy matching: lowercase, remove non-alphanumeric."""
    return re.sub(r"[^a-z]", "", s.lower())


# Keywords for fuzzy label matching. Ordered by specificity (most specific first).
# Each field has a list of keyword lists — ALL keywords in a sublist must be
# present for a match (AND logic), and ANY sublist matches (OR logic).
_LABEL_KEYWORDS: dict[str, list[list[str]]] = {
    "last_name": [["nom"], ["surname"]],
    "first_name": [["prenom"], ["prenoms"], ["given"], ["givennames"]],
    # "naissance" garbles to "maissanc", "naissanc", "smaissance" etc.
    # BUT only match as dob if "date" is also present — otherwise it's birth_place
    "dob": [["naissance", "date"], ["maissanc", "date"], ["naissanc", "date"],
            ["birth", "date"], ["datenaissance"], ["dateofbirth"], ["dateofviath"],
            ["datedsm"], ["dateds"]],
    # birth_place: "lieu de naissance" or "place of birth" — match on lieu or placeof
    # Also matches garbled "MaissancEiPiacrOf Biaty" via ["maissanc","piacr"]
    "birth_place": [["lieu"], ["placeofbirth"], ["lieunaissance"],
                    ["placeof", "birth"], ["naissance", "lieu"],
                    ["maissanc", "piacr"], ["maissanc", "piace"]],
    "sex": [["sexe"], ["sex"]],
    "height": [["taille"], ["height"]],
    "profession": [["profession"], ["occupation"]],
    "doc_number": [["identifiant"], ["uniqueidentifier"], ["identifiantunique"]],
    "father": [["pere"], ["father"]],
    "mother": [["mere"], ["mother"]],
    "issue_date": [["delivrance"], ["dateofissue"], ["datedelivrance"], ["delivranc"],
                   ["dateissue"]],
    "expiry": [["expiration"], ["expiry"], ["expire"], ["dateofexpiry"],
               ["xpiration"], ["xrhration"], ["dexpiration"]],
    # Generic "date" — used as a fallback for date fields
    "any_date": [["date"]],
}

# Fields that are dates — used for value-based fallback
_DATE_FIELDS = {"dob", "issue_date", "expiry"}

# Known label keywords — used to detect label-only lines (so we don't use
# them as values)
_ALL_LABEL_KEYWORDS = set()
for keywords_list in _LABEL_KEYWORDS.values():
    for kw_list in keywords_list:
        for kw in kw_list:
            _ALL_LABEL_KEYWORDS.add(kw)


def _fuzzy_match_label(line: str, field_name: str) -> bool:
    """Check if a line is a label for the given field using fuzzy matching."""
    normalized = _normalize_text(line)
    if not normalized:
        return False
    keyword_lists = _LABEL_KEYWORDS.get(field_name, [])
    for kw_list in keyword_lists:
        if all(kw in normalized for kw in kw_list):
            return True
    return False


def _is_any_label(line: str) -> bool:
    """Check if a line looks like any known label (not a value)."""
    stripped = line.strip()
    normalized = _normalize_text(stripped)

    # Pure digits / punctuation with no alpha: treat as potential values
    # (dates, document numbers), not labels.
    if not normalized:
        # If the stripped line has digits, it might be a date or number — not a label.
        # Only treat as label (skip) if there's truly nothing useful.
        return not bool(re.search(r"\d", stripped))

    # Check if the line matches any field's keywords
    for field_name in _LABEL_KEYWORDS:
        if _fuzzy_match_label(line, field_name):
            return True
    # Also check for common non-value lines
    for word in ["republique", "republic", "cameroun", "cameroon",
                 "autorite", "authority", "adresse", "address",
                 "signature", "poste", "identification"]:
        if word in normalized:
            return True
    return False


def _extract_field(lines: list[str], field_name: str) -> str | None:
    """Find a label line and extract the value from the same or next line.

    Uses fuzzy matching to identify the label, then extracts the value from
    the same line (after the label) or the next non-label line.
    """
    for i, line in enumerate(lines):
        if not _fuzzy_match_label(line, field_name):
            continue

        # Try same-line extraction: remove the label part and check if
        # there's a value remaining
        remaining = _strip_label_from_line(line, field_name)
        if remaining and not _is_any_label(remaining) and _has_value_content(remaining):
            return remaining

        # Try next-line extraction — skip noise/stray characters but only
        # break on genuine label lines (not pure digits/punctuation).
        for j in range(i + 1, min(i + 6, len(lines))):
            next_line = lines[j].strip()
            if not next_line:
                continue
            # Only stop scanning if we hit an actual keyword label.
            # Stray characters like '1', '0', 'n' are noise — skip them.
            norm = _normalize_text(next_line)
            if norm and _is_any_label(next_line):
                break  # hit another real label, stop
            if _has_value_content(next_line):
                return next_line

    return None


def _strip_label_from_line(line: str, field_name: str) -> str:
    """Remove the label portion from a line, returning the remaining text."""
    # Try to find where the label ends and the value begins
    # Common separators: / : - space
    # For bilingual labels like "NOM / SURNAME", the label is the whole thing
    # For "NOM: DOE", the label is "NOM:" and the value is "DOE"

    # If the line contains both French and English labels, it's likely a
    # label-only line — return empty
    normalized = _normalize_text(line)
    keyword_lists = _LABEL_KEYWORDS.get(field_name, [])

    # Check if multiple label keywords are present (bilingual label)
    match_count = 0
    for kw_list in keyword_lists:
        if all(kw in normalized for kw in kw_list):
            match_count += 1

    if match_count >= 2:
        # Bilingual label like "NOM / SURNAME" — likely label-only
        return ""

    # Try to split on common separators and take the part after the label
    for sep in [":", "-", "/"]:
        if sep in line:
            parts = line.split(sep)
            # Take the last non-empty part as the value
            for part in reversed(parts):
                part = part.strip()
                if part and not _is_any_label(part):
                    return part

    # If no separator, try to find the label keyword and take everything after
    for kw_list in keyword_lists:
        for kw in kw_list:
            # Find the keyword in the original line (case-insensitive)
            idx = line.lower().find(kw)
            if idx >= 0:
                remaining = line[idx + len(kw):].strip()
                # Remove leading separators
                remaining = remaining.lstrip("/: -")
                if remaining and not _is_any_label(remaining):
                    return remaining

    return ""


def _has_value_content(line: str) -> bool:
    """Check if a line has actual value content (not just noise/punctuation)."""
    stripped = line.strip()
    if not stripped:
        return False
    # Remove punctuation and check if there's alphanumeric content
    alnum = re.sub(r"[^a-zA-Z0-9À-ÿ]", "", stripped)
    if len(alnum) < 2:
        return False
    # Filter out single characters and pure punctuation
    if stripped in ["|", "—", "-", "/", ":", "."]:
        return False
    # Filter out very short numeric-only lines (likely noise)
    if stripped.isdigit() and len(stripped) < 3:
        return False
    return True


# ── Value-based fallback extraction ───────────────────────────────────────────

def _extract_dates_from_lines(lines: list[str]) -> list[str]:
    """Find all date-like values in the lines."""
    dates = []
    for line in lines:
        if not _has_value_content(line):
            continue
        if _is_any_label(line):
            continue
        m = _DATE_RE.search(line)
        if m:
            dates.append(m.group(1))
    return dates


def _extract_names_from_lines(lines: list[str]) -> list[str]:
    """Find all name-like values (uppercase letters, spaces, hyphens).

    Requires either multiple words or 6+ characters to filter out
    short OCR noise tokens like 'OiNel' or 'SpSM'.
    """
    names = []
    for line in lines:
        stripped = line.strip()
        if not _has_value_content(stripped):
            continue
        if _is_any_label(stripped):
            continue
        # Name pattern: starts uppercase, followed by letters/spaces/hyphens
        if re.match(r"^[A-ZÉÈÊËÀÂÙÛÜÏÎÇ][A-ZÉÈÊËÀÂÙÛÜÏÎÇa-zéèêëàâùûüïîç \-']+$", stripped):
            word_count = len(stripped.split())
            # Accept multi-word names OR single long names (≥6 chars)
            if word_count >= 2 or len(stripped) >= 6:
                names.append(stripped)
    return names


def _extract_numbers_from_lines(lines: list[str]) -> list[str]:
    """Find all long numeric values (potential document numbers).

    Handles cases where OCR inserts a '/' in the middle of a number,
    e.g. '202400065278/0002' → joined as '20240006527810002' to reconstruct
    the full identifier. Also returns each segment individually as fallback.
    """
    numbers = []
    for line in lines:
        stripped = line.strip()
        if not _has_value_content(stripped):
            continue
        if _is_any_label(stripped):
            continue
        # Check if the line looks like a split document number: digits/digits
        # e.g. "202400065278/0002" — join segments (drop the slash)
        slash_match = re.match(r"^(\d{6,})/(\d{4,})$", stripped)
        if slash_match:
            joined = slash_match.group(1) + slash_match.group(2)
            numbers.append(joined)
            continue
        # Find all digit runs of 6+ digits
        matches = re.findall(r"\d{6,20}", stripped)
        numbers.extend(matches)
    return numbers


# ── Name cleaning ─────────────────────────────────────────────────────────────

_LABEL_WORDS = {
    "nom", "surname", "prenom", "prenoms", "given", "names", "givennames",
    "igivn", "igiven",
    "date", "lieu", "sexe", "sex", "taille", "height", "profession",
    "occupation", "signature", "identifiant", "unique", "pere", "father",
    "mere", "mother", "birth", "place", "issue", "expiry", "expire",
    "valable", "delivrance", "naissanc", "expiration", "autorite",
    "authority", "adresse", "address", "republique", "republic",
    "cameroun", "cameroon", "poste", "identification",
}


def _clean_name(raw: str | None) -> str | None:
    """Clean up a name value: remove label words, trim, title-case."""
    if not raw:
        return None
    cleaned = raw.strip()
    # Remove label words (case-insensitive, word-boundary)
    for word in _LABEL_WORDS:
        cleaned = re.sub(rf"\b{word}\b", "", cleaned, flags=re.IGNORECASE)
    # Remove leading/trailing separators and whitespace
    cleaned = cleaned.strip(" /-:|")
    # Remove single leftover characters
    cleaned = re.sub(r"\b[a-z]\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    # Reject if the cleaned result is entirely composed of label-word fragments.
    # This catches garbled label artifacts like "Igiven" where word-boundary
    # regex doesn't fire because the label keyword is fused with a stray prefix
    # character (e.g. "given" inside "igiven").
    normalized_result = re.sub(r"[^a-z]", "", cleaned.lower())
    for word in _LABEL_WORDS:
        if (
            normalized_result == word
            or normalized_result.startswith(word)
            or normalized_result.endswith(word)
        ) and len(normalized_result) <= len(word) + 2:
            return None
    return cleaned.title()


# ── Main extraction ──────────────────────────────────────────────────────────

def _run_ocr(reader, img: np.ndarray) -> tuple[list[str], float]:
    """Run OCR on an image, return (lines, avg_confidence).

    Keeps ALL lines regardless of confidence — garbled labels often have
    low confidence but are still needed for field matching.
    """
    results = reader.readtext(img, detail=1, paragraph=False)
    lines = [text for (_, text, _conf) in results]
    avg_conf = sum(conf for (_, _, conf) in results) / max(len(results), 1)
    return lines, round(avg_conf, 3)


def _extract_from_lines(lines: list[str]) -> dict[str, str | None]:
    """Extract all fields from OCR lines using fuzzy label matching."""
    result: dict[str, str | None] = {}
    for field_name in _LABEL_KEYWORDS:
        if field_name == "any_date":
            continue
        result[field_name] = _extract_field(lines, field_name)
    return result


def _normalise_date_str(raw: str) -> str:
    """Normalise raw date string: collapse double separators, unify to dots."""
    raw = re.sub(r"[,\.]{2,}", ".", raw.strip())
    return raw.replace(",", ".")


def _correct_ocr_year(raw: str) -> str:
    """Fix common OCR year misreads for Cameroon CNI date range (1920–2040).

    Common misreads: 2034 → 2084 (3→8 digit), 2024 → 2074.
    Strategy: subtract decades until the year falls in a plausible CNI range.
    """
    def fix_year(m: re.Match) -> str:
        year = int(m.group(0))
        if year <= 2050:
            return m.group(0)  # already plausible, don't touch
        # Try subtracting 10, 20, 30 … until we land in 1920–2040
        for delta in range(10, 200, 10):
            candidate = year - delta
            if 1920 <= candidate <= 2040:
                return str(candidate)
        return m.group(0)
    return re.sub(r"\d{4}", fix_year, raw)


def _extract_doc_number_value(raw: str | None) -> str | None:
    if not raw:
        return None
    stripped = raw.strip()
    # Handle "digits/digits" — join them (OCR slash in middle of identifier)
    slash_match = re.match(r"^(\d{6,})/(\d{4,})$", stripped)
    if slash_match:
        return slash_match.group(1) + slash_match.group(2)
    m = _DOC_NUMBER_RE.search(stripped)
    return m.group(1) if m else None


def _extract_date_value(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _DATE_RE.search(raw)
    if not m:
        return None
    val = _normalise_date_str(m.group(1))
    # If normalised date doesn't parse (e.g. year out of range), try correction
    if not _parse_date(val):
        val = _correct_ocr_year(val)
    return val


def _extract_height_value(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _HEIGHT_RE.search(raw)
    return m.group(1) if m else None


def extract_from_cni(front_b64: str, back_b64: str | None = None,
                     doc_type: str = "national_id") -> DocumentFields:
    """Run OCR on CNI or Passport image(s) and extract structured fields.

    Front side: name, first name, DOB, birth place, sex, height, profession.
    Back side: father, mother, issue date, expiry date, unique identifier.

    Uses fuzzy label matching + value-based fallback for robust extraction.
    """
    reader = _get_reader()

    # ── Front side ────────────────────────────────────────────────────────────
    front_img = _preprocess_image(_decode_image(front_b64))
    front_lines, front_conf = _run_ocr(reader, front_img)

    fields = DocumentFields(
        type=doc_type, raw_text=front_lines, confidence=front_conf
    )

    # Extract front-side fields via fuzzy label matching
    front_data = _extract_from_lines(front_lines)

    # Last name
    if raw := front_data.get("last_name"):
        fields.last_name = _clean_name(raw)

    # First name
    if raw := front_data.get("first_name"):
        fields.first_name = _clean_name(raw)

    # Date of birth
    if raw := front_data.get("dob"):
        raw_dob = _extract_date_value(raw)
        if raw_dob:
            # Normalise separators before storing (e.g. "23,.09.2004" → "23.09.2004")
            raw_dob = re.sub(r"[,\.]{2,}", ".", raw_dob).replace(",", ".")
            fields.date_of_birth = raw_dob
            parsed = _parse_date(raw_dob)
            if parsed:
                fields.age = _compute_age(parsed)
                fields.is_underage = fields.age < 18

    # Birth place
    if raw := front_data.get("birth_place"):
        cleaned = raw.strip().title()
        first_word = cleaned.split()[0] if cleaned.split() else ""
        # A valid place name starts uppercase with ≥3 chars and doesn't
        # contain known garbled OCR artifacts (piacr, eipiacr, etc.)
        norm_check = re.sub(r"[^a-z]", "", cleaned.lower())
        garbled = any(g in norm_check for g in ["piacr", "piace", "maissanc"])
        if (len(cleaned) >= 3
                and not cleaned[0].isdigit()
                and len(first_word) >= 3
                and not garbled):
            fields.birth_place = cleaned

    # Birth place fallback: scan front lines for a value right after a
    # birth_place label, skipping garbled same-line extractions.
    if not fields.birth_place:
        for i, line in enumerate(front_lines):
            if _fuzzy_match_label(line, "birth_place"):
                # Look ahead for the next short uppercase place name
                for j in range(i + 1, min(i + 6, len(front_lines))):
                    nxt = front_lines[j].strip()
                    if not nxt or not _has_value_content(nxt):
                        continue
                    norm_nxt = re.sub(r"[^a-z]", "", nxt.lower())
                    if _is_any_label(nxt) and norm_nxt:
                        break
                    # Accept if it looks like a place name (all-caps, short, no digits)
                    if (re.match(r"^[A-ZÉÈÊËÀÂÙÛÜÏÎÇ][A-ZÉÈÊËÀÂÙÛÜÏÎÇa-z \-']+$", nxt)
                            and len(nxt) >= 3 and len(nxt.split()) <= 3
                            and not any(g in norm_nxt for g in ["piacr", "piace", "maissanc"])):
                        fields.birth_place = nxt.title()
                        break
                break

    # Sex
    if raw := front_data.get("sex"):
        # Sex must be a single letter M or F — reject garbled multi-word values
        candidate = raw.strip().upper()
        for ch in candidate:
            if ch in ("M", "F"):
                fields.sex = ch
                break

    # Height
    if raw := front_data.get("height"):
        h = _extract_height_value(raw)
        if h:
            try:
                # Plausible height: 100–220 cm
                if 100 <= float(h.replace(",", ".")) <= 220:
                    fields.height = h
            except ValueError:
                pass

    # Profession
    if raw := front_data.get("profession"):
        cleaned = raw.strip().title()
        if cleaned and len(cleaned) > 1:
            fields.profession = cleaned

    # Document number (may be on front or back)
    if raw := front_data.get("doc_number"):
        fields.document_number = _extract_doc_number_value(raw)

    # Expiry date (may be on front or back)
    if raw := front_data.get("expiry"):
        raw_exp = _extract_date_value(raw)
        if raw_exp:
            fields.expiry_date = raw_exp
            parsed_exp = _parse_date(raw_exp)
            if parsed_exp:
                fields.is_expired = parsed_exp < date.today()

    # Issue date (usually on back)
    if raw := front_data.get("issue_date"):
        raw_issue = _extract_date_value(raw)
        if raw_issue:
            fields.issue_date = raw_issue

    # ── Value-based fallback for front side ───────────────────────────────────
    # If label matching failed, try extracting values by format
    if not fields.first_name and not fields.last_name:
        names = _extract_names_from_lines(front_lines)
        if names:
            # First name is usually the first name-like value after PRENOMS
            fields.first_name = _clean_name(names[0])

    if not fields.date_of_birth:
        dates = _extract_dates_from_lines(front_lines)
        if dates:
            norm = _extract_date_value(dates[0])
            if norm:
                fields.date_of_birth = norm
                parsed = _parse_date(norm)
                if parsed:
                    fields.age = _compute_age(parsed)
                    fields.is_underage = fields.age < 18

    if not fields.height:
        for line in front_lines:
            if _has_value_content(line) and not _is_any_label(line):
                m = _HEIGHT_RE.search(line)
                if m and "," in line:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 100 <= val <= 220:
                            fields.height = m.group(1)
                            break
                    except ValueError:
                        pass

    # ── Back side ─────────────────────────────────────────────────────────────
    if back_b64:
        back_img = _preprocess_image(_decode_image(back_b64))
        back_lines, back_conf = _run_ocr(reader, back_img)
        fields.raw_text_back = back_lines
        # Average confidence across both sides
        fields.confidence = round((front_conf + back_conf) / 2, 3)

        back_data = _extract_from_lines(back_lines)

        # Father
        if raw := back_data.get("father"):
            fields.father = _clean_name(raw)

        # Mother
        if raw := back_data.get("mother"):
            fields.mother = _clean_name(raw)

        # Issue date (if not found on front)
        if not fields.issue_date:
            if raw := back_data.get("issue_date"):
                raw_issue = _extract_date_value(raw)
                if raw_issue and _parse_date(raw_issue):
                    fields.issue_date = raw_issue

        # Expiry date (if not found on front)
        if not fields.expiry_date:
            if raw := back_data.get("expiry"):
                raw_exp = _extract_date_value(raw)
                if raw_exp and _parse_date(raw_exp):
                    fields.expiry_date = raw_exp
                    parsed_exp = _parse_date(raw_exp)
                    if parsed_exp:
                        fields.is_expired = parsed_exp < date.today()

        # Document number (if not found on front)
        if not fields.document_number:
            if raw := back_data.get("doc_number"):
                fields.document_number = _extract_doc_number_value(raw)

        # ── Value-based fallback for back side ─────────────────────────────────
        # On Cameroonian CNI, PERE/MERE values often appear BEFORE their labels.
        # Collect all name-like lines from the back as candidates.
        if not fields.father or not fields.mother:
            back_names = _extract_names_from_lines(back_lines)
            # Filter out names already assigned and known non-person strings
            _exclude = {fields.father, fields.mother,
                        fields.first_name, fields.last_name}
            remaining_names = [n for n in back_names if n not in _exclude]
            if not fields.father and remaining_names:
                fields.father = _clean_name(remaining_names[0])
            if not fields.mother and len(remaining_names) > 1:
                fields.mother = _clean_name(remaining_names[1])

        # If dates not found, try date-based extraction
        if not fields.issue_date or not fields.expiry_date:
            back_dates = _extract_dates_from_lines(back_lines)
            if not fields.issue_date and back_dates:
                # Normalise and validate before storing
                norm = _extract_date_value(back_dates[0])
                if norm and _parse_date(norm):
                    fields.issue_date = norm
            if not fields.expiry_date and len(back_dates) > 1:
                norm = _extract_date_value(back_dates[1])
                if norm:
                    fields.expiry_date = norm
                    parsed_exp = _parse_date(norm)
                    if parsed_exp:
                        fields.is_expired = parsed_exp < date.today()

        # If document number not found, try number-based extraction
        if not fields.document_number:
            back_numbers = _extract_numbers_from_lines(back_lines)
            # Prefer the longest number (unique identifier is usually long)
            if back_numbers:
                back_numbers.sort(key=len, reverse=True)
                fields.document_number = back_numbers[0]

    return fields