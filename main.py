import logging
import sys
from pathlib import Path
from typing import List
 
import config
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
 
from core.extractor  import process_resume
from core.normalizer import normalize
from core.matcher    import match_fields, build_payload
from core.filler     import apply_fill, build_fill_report
from models.form_field  import FormField, FilledField
from models.parsed_data import ParsedResume
 
# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level   = config.LOG_LEVEL,
    format  = "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("autofill")
 
# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(title="Resume Autofill Engine", version="3.0")
 
# CORS — required so the Chrome extension can call localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# ─────────────────────────────────────────────────────────────
# All canonical field keys with their human-readable labels.
# This is the master list that drives the payload sent to the
# extension. Add new fields here — no other file needs changing.
# ─────────────────────────────────────────────────────────────
FIELD_DEFINITIONS: List[dict] = [
    # ── Name ────────────────────────────────────────────────
    {"key": "full_name",    "label": "Full Name"},
    {"key": "first_name",   "label": "First Name"},
    {"key": "middle_name",  "label": "Middle Name"},
    {"key": "last_name",    "label": "Last Name"},
 
    # ── Personal ─────────────────────────────────────────────
    {"key": "gender",         "label": "Gender"},
    {"key": "blood_group",    "label": "Blood Group"},
    {"key": "dob",            "label": "Date of Birth"},
    {"key": "age",            "label": "Age"},
    {"key": "nationality",    "label": "Nationality"},
    {"key": "mother_tongue",  "label": "Mother Tongue"},
    {"key": "email",          "label": "Email"},
    {"key": "religion",       "label": "Religion"},
    {"key": "marital_status", "label": "Marital Status"},
    {"key": "aadhar",         "label": "Aadhaar Number"},
    {"key": "caste_category", "label": "Caste Category"},
 
    # ── Contact ───────────────────────────────────────────────
    {"key": "phone",           "label": "Mobile Number"},
    {"key": "alternate_phone", "label": "Alternate Mobile"},
 
    # ── Parent / Guardian ────────────────────────────────────
    {"key": "father_name",       "label": "Father / Guardian Name"},
    {"key": "father_mobile",     "label": "Father Mobile"},
    {"key": "father_occupation", "label": "Father Occupation"},
    {"key": "mother_name",       "label": "Mother / Guardian Name"},
    {"key": "mother_mobile",     "label": "Mother Mobile"},
    {"key": "mother_occupation", "label": "Mother Occupation"},
    {"key": "guardian_email",    "label": "Parent / Guardian Email"},
 
    # ── Emergency Contact ─────────────────────────────────────
    {"key": "emergency_contact_name",   "label": "Emergency Contact Name"},
    {"key": "emergency_contact_number", "label": "Emergency Contact Number"},
    {"key": "relationship",             "label": "Relationship"},
 
    # ── Address ──────────────────────────────────────────────
    {"key": "address",   "label": "Full Address"},
    {"key": "house_no",  "label": "House No"},
    {"key": "street",    "label": "Street / Locality"},
    {"key": "city",      "label": "City / Town"},
    {"key": "mandal",    "label": "Mandal / Taluk"},
    {"key": "district",  "label": "District"},
    {"key": "state",     "label": "State"},
    {"key": "country",   "label": "Country"},
    {"key": "pincode",   "label": "Pin Code"},
 
    # ── Academic ─────────────────────────────────────────────
    {"key": "class_",            "label": "Class"},
    {"key": "section",           "label": "Section"},
    {"key": "admission_number",  "label": "Admission Number"},
    {"key": "academic_year",     "label": "Academic Year"},
    {"key": "medium",            "label": "Medium of Instruction"},
    {"key": "date_of_admission", "label": "Date of Admission"},
    {"key": "previous_school",   "label": "Previous School Name"},
    {"key": "tc_number",         "label": "TC Number"},
 
    # ── Health / Emergency / Transport ───────────────────────
    {"key": "allergies",          "label": "Allergies Details"},
    {"key": "medical_conditions", "label": "Medical Conditions"},
    {"key": "nearest_hospital",   "label": "Nearest Hospital / Doctor"},
    {"key": "transport_mode",     "label": "Mode of Transport"},
    {"key": "bus_route",          "label": "Bus Route / Vehicle Number"},
    {"key": "hostel",             "label": "Hostel / Day Scholar"},
 
    # ── Professional / Universal ─────────────────────────────
    {"key": "website",          "label": "Website"},
    {"key": "linkedin",         "label": "LinkedIn"},
    {"key": "pan_number",       "label": "PAN Number"},
    {"key": "passport_number",  "label": "Passport Number"},
    {"key": "voter_id",         "label": "Voter ID"},
    {"key": "driving_license",  "label": "Driving License"},
    {"key": "employee_id",      "label": "Employee ID"},
    {"key": "department",       "label": "Department"},
    {"key": "designation",      "label": "Designation"},
    {"key": "annual_income",    "label": "Annual Income"},
    {"key": "bank_account",     "label": "Bank Account Number"},
    {"key": "ifsc_code",        "label": "IFSC Code"},
    {"key": "branch_id",        "label": "Branch ID"},
]
 
 
# ─────────────────────────────────────────────────────────────
# Build the autofill payload from a normalised ParsedResume.
# Returns the flat dict used by the Chrome extension.
# ─────────────────────────────────────────────────────────────
 
def build_extension_payload(resume: ParsedResume) -> dict:
    """
    Returns:
        {
          "full_name": { "label": "Full Name", "value": "Aditya Kumar",
                         "confidence": 1.0, "key": "full_name" },
          ...
        }
    Only non-empty values are included.
    """
    # Get all values from the matcher's payload builder
    raw_values = build_payload(resume)   # from core/matcher.py
 
    result = {}
    for field in FIELD_DEFINITIONS:
        key   = field["key"]
        label = field["label"]
        value = raw_values.get(key, "")
 
        # DOB: pass as dict so content.js can pick the right format
        if key == "dob":
            dob = resume.dob
            if dob and dob.dd_mm_yyyy:
                value = {
                    "dd-mm-yyyy": dob.dd_mm_yyyy,
                    "dd/mm/yyyy": dob.dd_slash   or dob.dd_mm_yyyy,
                    "mm/dd/yyyy": dob.mm_slash   or dob.dd_mm_yyyy,
                    "yyyy-mm-dd": dob.yyyy_mm_dd or dob.dd_mm_yyyy,
                }
            else:
                continue
 
        if not value and value != 0:
            continue  # skip empty — blank-if-missing policy
 
        result[key] = {
            "label":      label,
            "value":      value,
            "confidence": 1.0,   # extracted from PDF directly — high confidence
            "key":        key,
        }
 
    return result
 
 
# ─────────────────────────────────────────────────────────────
# Core pipeline
# ─────────────────────────────────────────────────────────────
 
def run_autofill_pipeline(file_bytes: bytes) -> dict:
    try:
        log.info("Extracting from PDF (%d bytes)", len(file_bytes))
        raw = process_resume(file_bytes)
        if raw.get("status") != "success":
            raise ValueError(raw.get("error", "Extraction failed"))
 
        resume: ParsedResume = normalize(raw["data"])
        payload = build_extension_payload(resume)
 
        filled  = sum(1 for v in payload.values() if v.get("value"))
        report  = {
            "total":   len(FIELD_DEFINITIONS),
            "filled":  filled,
            "skipped": 0,
            "empty":   len(FIELD_DEFINITIONS) - filled,
        }
 
        log.info("Extracted %d / %d fields", filled, len(FIELD_DEFINITIONS))
        return {"status": "success", "payload": payload, "report": report}
 
    except Exception as exc:
        log.exception("Pipeline failed: %s", exc)
        return {"status": "error", "error": str(exc), "payload": {}, "report": {}}
 
 
# ─────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────
 
@app.post("/autofill")
async def api_autofill(file: UploadFile = File(...)):
    """
    POST /autofill
    Upload a PDF → returns autofill payload for the Chrome extension.
    """
    content = await file.read()
    return run_autofill_pipeline(content)
 
 
@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0"}
 
 
# ─────────────────────────────────────────────────────────────
# CLI — for quick testing without the extension
# Usage: python main.py resume.pdf
# ─────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <resume.pdf>")
        sys.exit(1)
 
    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)
 
    with open(pdf_path, "rb") as fh:
        result = run_autofill_pipeline(fh.read())
 
    if result["status"] != "success":
        print(f"ERROR: {result['error']}")
        sys.exit(1)
 
    payload = result["payload"]
    print(f"\n{'KEY':<28} {'LABEL':<32} {'VALUE'}")
    print("─" * 90)
    for key, info in payload.items():
        val = info["value"]
        if isinstance(val, dict):
            val = val.get("dd-mm-yyyy", str(val))
        print(f"{key:<28} {info['label']:<32} {str(val)[:40]}")
 
    r = result["report"]
    print(f"\nExtracted {r['filled']} / {r['total']} fields  "
          f"({r['empty']} empty)\n")