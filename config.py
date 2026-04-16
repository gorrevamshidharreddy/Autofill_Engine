"""
config.py
=========
Central configuration for the autofill engine.
Edit this file to tune thresholds, paths, and behaviour.
"""

from pathlib import Path

# ── Project root ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# ── Fuzzy-match confidence thresholds (0–100 scale) ──────────
# Scores come from rapidfuzz.fuzz.WRatio (0–100)
THRESHOLD_HIGH   = 88   # fill without any warning
THRESHOLD_MEDIUM = 72   # fill, flag in report as "medium confidence"
THRESHOLD_LOW    = 55   # fill, flag as "low confidence"
THRESHOLD_SKIP   = 54   # do NOT fill — no recognisable match

# ── PDF extraction ────────────────────────────────────────────
OCR_FALLBACK     = True    # use pytesseract when pdfplumber gets no text
OCR_RESOLUTION   = 200     # DPI for page rasterisation

# ── Date convention ───────────────────────────────────────────
DAYFIRST = True            # True = DD-MM-YYYY (Indian default)

# ── Address defaults ──────────────────────────────────────────
DEFAULT_COUNTRY = "India"

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL  = "INFO"        # DEBUG | INFO | WARNING | ERROR
LOG_FILE   = BASE_DIR / "autofill.log"