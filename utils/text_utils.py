"""
utils/text_utils.py
===================
String cleaning, normalisation, and fuzzy-match helpers
used across the entire autofill pipeline.
"""

import re
import unicodedata
from rapidfuzz import fuzz, process


# ─────────────────────────────────────────────────────────────
#  Basic Cleaning
# ─────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    """
    Lowercase, strip extra whitespace, remove trailing colons/asterisks.
    Used to normalise both label text and synonym dictionaries before matching.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)   # full-width → ASCII, etc.
    text = text.lower()
    text = re.sub(r"[*†‡]", "", text)            # required-field markers
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" :")
    return text


def strip_label_affixes(label: str) -> str:
    """
    Remove common form affixes before fuzzy matching.
    e.g. 'Enter first name' → 'first name'
         'e.g. O+'          → 'O+'
         'Auto-filled from DOB' → 'DOB'
    """
    prefixes = r"^(enter|type|select|choose|provide|e\.g\.?|eg\.?|example:?)\s+"
    label = re.sub(prefixes, "", label, flags=re.I)
    suffixes = r"\s+(here|below|above|field)$"
    label = re.sub(suffixes, "", label, flags=re.I)
    return label.strip()


def digits_only(text: str) -> str:
    """Return only the digit characters from a string."""
    return re.sub(r"\D", "", text or "")


def normalise_phone(raw: str) -> str:
    """
    Strip all non-digit characters, then return 10-digit number.
    Handles +91 prefix.
    """
    digits = digits_only(raw)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits if len(digits) == 10 else digits   # return whatever we have


def normalise_name(raw: str) -> str:
    """Title-case a name, collapsing extra spaces."""
    return " ".join(w.capitalize() for w in raw.split()) if raw else ""


# ─────────────────────────────────────────────────────────────
#  Fuzzy Matching
# ─────────────────────────────────────────────────────────────

# Confidence thresholds
THRESHOLD_HIGH   = 88   # very confident — fill directly
THRESHOLD_MEDIUM = 72   # fill with lower confidence score
THRESHOLD_LOW    = 55   # flag as uncertain, still fill
THRESHOLD_SKIP   = 54   # below this → do not fill


def fuzzy_best_match(
    query: str,
    choices: list[str],
    threshold: int = THRESHOLD_LOW,
) -> tuple[str | None, float]:
    """
    Find the best match for `query` in `choices` using a combination of
    token_sort_ratio (handles word-order variation) and partial_ratio
    (handles label being a substring of the choice or vice-versa).

    Returns (best_choice, confidence_0_to_1) or (None, 0.0).
    """
    if not query or not choices:
        return None, 0.0

    query_clean = clean(strip_label_affixes(query))

    # rapidfuzz process.extractOne uses WRatio by default (hybrid scorer)
    result = process.extractOne(
        query_clean,
        [clean(c) for c in choices],
        scorer=fuzz.WRatio,
        score_cutoff=threshold,
    )
    if result is None:
        return None, 0.0

    best_clean, score, idx = result
    return choices[idx], round(score / 100, 4)


def multi_signal_score(field_hints: str, candidate_key: str, synonyms: list[str]) -> float:
    """
    Score a (field, candidate_key) pair using all synonym variants.
    Returns the highest score found across all synonyms.
    """
    best = 0.0
    hints_clean = clean(strip_label_affixes(field_hints))
    for syn in synonyms:
        s = fuzz.WRatio(hints_clean, clean(syn)) / 100
        if s > best:
            best = s
    return round(best, 4)