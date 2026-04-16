import re
from models.form_field import FormField, FilledField
from utils.text_utils import fuzzy_best_match, digits_only, clean
from utils.date_utils import detect_date_format_from_placeholder, format_date
from models.parsed_data import ParsedResume


# ─────────────────────────────────────────────────────────────
#  Value formatters
# ─────────────────────────────────────────────────────────────

def format_aadhar(raw: str, spaced: bool = False) -> str:
    """
    raw    : 12 raw digits
    spaced : if True → "XXXX XXXX XXXX", else → "XXXXXXXXXXXX"
    """
    digits = digits_only(raw)
    if len(digits) != 12:
        return raw
    if spaced:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return digits


def format_phone(raw: str, with_country_code: bool = False) -> str:
    digits = digits_only(raw)
    if not digits:
        return raw
    if with_country_code and not digits.startswith("91"):
        return "+91" + digits
    return digits


def format_pincode(raw: str) -> str:
    digits = digits_only(raw)
    return digits if len(digits) == 6 else ""


def resolve_select_option(value: str, options: list[str]) -> str:
    """
    Match the extracted value to the closest option in a dropdown.
    e.g. "Male" → "Male", "MALE" → "Male", "m" → "Male"
    """
    if not options or not value:
        return value

    best, score = fuzzy_best_match(value, options, threshold=50)
    return best if best else value


# ─────────────────────────────────────────────────────────────
#  Field-type specific filling
# ─────────────────────────────────────────────────────────────

def _fill_text(field: FormField, raw_value: str) -> str:
    """General text field — return value as-is (already cleaned by normalizer)."""
    return raw_value.strip()


def _fill_date(field: FormField, raw_value: str, resume: ParsedResume) -> str:
    """Detect format from placeholder and reformat DOB."""
    placeholder = field.placeholder or ""
    fmt = detect_date_format_from_placeholder(placeholder)
    return format_date(resume.dob, fmt) or raw_value


def _fill_select(field: FormField, raw_value: str) -> str:
    """Fuzzy-match raw_value against available dropdown options."""
    if field.options:
        return resolve_select_option(raw_value, field.options)
    return raw_value


def _fill_tel(field: FormField, raw_value: str) -> str:
    """Phone / mobile fields."""
    digits = digits_only(raw_value)
    # If placeholder shows '+91' style, add country code
    if field.placeholder and "+91" in field.placeholder:
        return format_phone(digits, with_country_code=True)
    return digits


def _fill_number(field: FormField, raw_value: str) -> str:
    """Numeric fields — return digits only."""
    return digits_only(raw_value) or raw_value


# ─────────────────────────────────────────────────────────────
#  Special key overrides
# ─────────────────────────────────────────────────────────────

_KEY_FORMATTERS = {
    "aadhar":           lambda f, v, r: format_aadhar(v, spaced=True),
    "pincode":          lambda f, v, r: format_pincode(v),
    "phone":            lambda f, v, r: _fill_tel(f, v),
    "father_mobile":    lambda f, v, r: _fill_tel(f, v),
    "mother_mobile":    lambda f, v, r: _fill_tel(f, v),
    "emergency_contact_number": lambda f, v, r: _fill_tel(f, v),
    "dob":              lambda f, v, r: _fill_date(f, v, r),
}


# ─────────────────────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────────────────────

def apply_fill(
    filled_fields: list[FilledField],
    resume: ParsedResume,
) -> list[FilledField]:
    """
    Post-process each FilledField to produce a final fill_value
    that's ready to inject into the form element.

    Returns the same list with fill_value updated in-place.
    """
    for ff in filled_fields:
        if ff.skipped or not ff.matched_key:
            continue

        field = ff.field
        key   = ff.matched_key
        value = ff.fill_value or ""

        # ── Key-specific formatters (highest priority) ────────
        if key in _KEY_FORMATTERS:
            ff.fill_value = _KEY_FORMATTERS[key](field, value, resume)
            continue

        # ── Field-type formatters ─────────────────────────────
        ftype = field.field_type

        if ftype == "select":
            ff.fill_value = _fill_select(field, value)
        elif ftype == "tel":
            ff.fill_value = _fill_tel(field, value)
        elif ftype == "number":
            ff.fill_value = _fill_number(field, value)
        elif ftype == "date":
            ff.fill_value = _fill_date(field, value, resume)
        elif ftype == "email":
            ff.fill_value = value.lower().strip()
        else:
            ff.fill_value = _fill_text(field, value)

        # ── Final guard: never fill with empty / placeholder ──
        if ff.fill_value == field.placeholder:
            ff.fill_value = ""

    return filled_fields


def build_fill_report(filled_fields: list[FilledField]) -> dict:
    """
    Summarise fill results for logging / debugging.
    """
    filled  = [f for f in filled_fields if not f.skipped and f.fill_value]
    skipped = [f for f in filled_fields if f.skipped]
    empty   = [f for f in filled_fields if not f.skipped and not f.fill_value]

    return {
        "total":   len(filled_fields),
        "filled":  len(filled),
        "skipped": len(skipped),
        "empty":   len(empty),
        "details": [
            {
                "label":      f.field.label,
                "key":        f.matched_key,
                "value":      f.fill_value,
                "confidence": round(f.confidence, 2),
                "skipped":    f.skipped,
                "reason":     f.skip_reason,
            }
            for f in filled_fields
        ],
    }