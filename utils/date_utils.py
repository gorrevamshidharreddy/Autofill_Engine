"""
utils/date_utils.py
===================
Date parsing, age calculation, and multi-format output helpers.
"""

import re
from datetime import date
from dateutil import parser as date_parser
from models.parsed_data import DOBData


# Supported output formats — keys match DOBData fields and autofill payload keys
DATE_FORMATS = {
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd/mm/yyyy": "%d/%m/%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "yyyy-mm-dd": "%Y-%m-%d",
    "dd mm yyyy": "%d %m %Y",
    "mmm dd yyyy": "%b %d %Y",       # Apr 14 2000
}

# Regexes for common date patterns (tried in order before dateutil fallback)
_DATE_PATTERNS = [
    r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b',    # DD/MM/YYYY or MM/DD/YYYY
    r'\b(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})\b',    # YYYY-MM-DD
    r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})\b',
    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2}),?\s+(\d{4})\b',
]


def parse_date(raw: str, dayfirst: bool = True) -> DOBData:
    """
    Parse a raw date string into a DOBData object with all format variants.
    `dayfirst=True` assumes DD-MM-YYYY (Indian convention).
    """
    if not raw or not raw.strip():
        return DOBData()

    raw = raw.strip()

    # Try dateutil — robust for most formats
    try:
        parsed = date_parser.parse(raw, fuzzy=True, dayfirst=dayfirst)
        age = (date.today() - parsed.date()).days // 365
        return DOBData(
            raw        = raw,
            dd_mm_yyyy = parsed.strftime("%d-%m-%Y"),
            dd_slash   = parsed.strftime("%d/%m/%Y"),
            mm_slash   = parsed.strftime("%m/%d/%Y"),
            yyyy_mm_dd = parsed.strftime("%Y-%m-%d"),
            age        = str(age) if 0 < age < 150 else "",
        )
    except (ValueError, OverflowError):
        pass

    return DOBData(raw=raw)


def format_date(dob: DOBData, target_format: str) -> str:
    """
    Return the DOBData value in whichever format the form expects.

    target_format is detected from the field's placeholder text, e.g.
    "dd-mm-yyyy", "mm/dd/yyyy", "yyyy-mm-dd".
    Falls back to dd-mm-yyyy.
    """
    fmt = target_format.lower().replace(" ", "").replace("-", "").replace("/", "")

    mapping = {
        "ddmmyyyy": dob.dd_mm_yyyy,
        "mmddyyyy": dob.mm_slash,
        "yyyymmdd": dob.yyyy_mm_dd,
    }
    return mapping.get(fmt, dob.dd_mm_yyyy) or dob.raw or ""


def detect_date_format_from_placeholder(placeholder: str) -> str:
    """
    Guess the expected date format from a field's placeholder text.
    e.g. "dd-mm-yyyy" → "ddmmyyyy"
         "YYYY/MM/DD" → "yyyymmdd"
    """
    if not placeholder:
        return "ddmmyyyy"

    ph = placeholder.lower()

    if re.search(r'yyyy[\-\/]mm[\-\/]dd', ph):
        return "yyyymmdd"
    if re.search(r'mm[\-\/]dd[\-\/]yyyy', ph):
        return "mmddyyyy"
    # Default Indian convention
    return "ddmmyyyy"