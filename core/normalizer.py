import re
from models.parsed_data import (
    ParsedResume, NameData, DOBData, AddressData,
    EducationEntry, ExperienceEntry,
)
from utils.text_utils import normalise_name, normalise_phone, digits_only

# Values that mean "empty" — never pass these to the form filler
_EMPTY = {"none", "n/a", "na", "nil", "-", "—", "not applicable", ""}


def _s(v) -> str:
    """Safe string clean."""
    val = str(v).strip() if v else ""
    return "" if val.lower() in _EMPTY else val


def _validate_aadhar(raw: str) -> str:
    digits = digits_only(raw or "")
    return digits if len(digits) == 12 else ""


def _validate_email(raw: str) -> str:
    m = re.search(r'[\w.\-+]+@[\w.\-]+\.\w{2,}', raw or "")
    return m.group().lower() if m else ""


def _validate_pincode(raw: str) -> str:
    digits = digits_only(raw or "")
    return digits if len(digits) == 6 else ""


def normalize(raw: dict) -> ParsedResume:
    """
    Parameters
    ----------
    raw : dict
        The `data` key from extractor.process_resume(file_bytes)

    Returns
    -------
    ParsedResume — fully validated and typed model
    """

    # ── Name ──────────────────────────────────────────────────
    raw_name = raw.get("name", {})
    if isinstance(raw_name, dict):
        name = NameData(
            full   = normalise_name(_s(raw_name.get("full"))),
            first  = normalise_name(_s(raw_name.get("first"))),
            middle = normalise_name(_s(raw_name.get("middle"))),
            last   = normalise_name(_s(raw_name.get("last"))),
        )
    else:
        parts = str(raw_name).split()
        name  = NameData(
            full  = normalise_name(str(raw_name)),
            first = parts[0] if parts else "",
            last  = parts[-1] if len(parts) > 1 else "",
        )

    # ── DOB ───────────────────────────────────────────────────
    raw_dob = raw.get("dob", {})
    if isinstance(raw_dob, dict):
        dob = DOBData(
            raw        = _s(raw_dob.get("raw")),
            dd_mm_yyyy = _s(raw_dob.get("dd-mm-yyyy") or raw_dob.get("dd_mm_yyyy")),
            dd_slash   = _s(raw_dob.get("dd/mm/yyyy") or raw_dob.get("dd_slash")),
            mm_slash   = _s(raw_dob.get("mm/dd/yyyy") or raw_dob.get("mm_slash")),
            yyyy_mm_dd = _s(raw_dob.get("yyyy-mm-dd") or raw_dob.get("yyyy_mm_dd")),
            age        = _s(raw_dob.get("age")),
        )
    else:
        from utils.date_utils import parse_date
        dob = parse_date(str(raw_dob))

    # ── Address ───────────────────────────────────────────────
    raw_addr = raw.get("address", {})
    if isinstance(raw_addr, dict):
        address = AddressData(
            full     = _s(raw_addr.get("full")),
            house_no = _s(raw_addr.get("house_no")),
            street   = _s(raw_addr.get("street")),
            city     = _s(raw_addr.get("city")),
            mandal   = _s(raw_addr.get("mandal")),
            district = _s(raw_addr.get("district")),
            state    = _s(raw_addr.get("state")),
            country  = _s(raw_addr.get("country")),
            pincode  = _validate_pincode(raw_addr.get("pincode", "")),
        )
    else:
        address = AddressData(full=_s(str(raw_addr)))

    # Rebuild full if empty
    if not address.full:
        parts = [address.house_no, address.street, address.city,
                 address.mandal, address.district, address.state,
                 address.country, address.pincode]
        address.full = ", ".join(p for p in parts if p)

    # ── Education ─────────────────────────────────────────────
    edu_entries = []
    for e in raw.get("education", []):
        if isinstance(e, dict):
            edu_entries.append(EducationEntry(
                degree      = _s(e.get("degree")),
                institution = _s(e.get("institution")),
                year        = _s(e.get("year")),
                grade       = _s(e.get("grade")),
                raw         = _s(e.get("raw")),
            ))

    # ── Experience ────────────────────────────────────────────
    exp_entries = []
    for e in raw.get("experience", []):
        if isinstance(e, dict):
            exp_entries.append(ExperienceEntry(
                role        = _s(e.get("role")),
                company     = _s(e.get("company")),
                duration    = _s(e.get("duration")),
                description = [_s(d) for d in e.get("description", []) if _s(d)],
            ))

    return ParsedResume(
        # Name
        name             = name,
        # Personal
        gender           = _s(raw.get("gender")),
        blood_group      = _s(raw.get("blood_group")),
        dob              = dob,
        nationality      = _s(raw.get("nationality")),
        mother_tongue    = _s(raw.get("mother_tongue")),
        religion         = _s(raw.get("religion")),
        caste_category   = _s(raw.get("caste_category")),
        aadhar           = _validate_aadhar(raw.get("aadhar", "")),
        # Contact
        email            = _validate_email(raw.get("email", "")),
        phone            = normalise_phone(raw.get("phone", "")),
        # Academic
        class_           = _s(raw.get("class")),
        section          = _s(raw.get("section")),
        admission_number = _s(raw.get("admission_number")),
        academic_year    = _s(raw.get("academic_year")),
        medium           = _s(raw.get("medium")),
        date_of_admission= _s(raw.get("date_of_admission")),
        previous_school  = _s(raw.get("previous_school")),
        tc_number        = _s(raw.get("tc_number", "")),
        # Parent / Guardian
        father_name      = normalise_name(_s(raw.get("father_name", ""))),
        father_mobile    = normalise_phone(raw.get("father_mobile", "")),
        father_occupation= _s(raw.get("father_occupation")),
        mother_name      = normalise_name(_s(raw.get("mother_name", ""))),
        mother_mobile    = normalise_phone(raw.get("mother_mobile", "")),
        mother_occupation= _s(raw.get("mother_occupation")),
        guardian_email   = _validate_email(raw.get("guardian_email", "")),
        # Address
        address          = address,
        # Health / Emergency / Transport
        allergies                = _s(raw.get("allergies")),
        medical_conditions       = _s(raw.get("medical_conditions")),
        emergency_contact_name   = normalise_name(_s(raw.get("emergency_contact_name", ""))),
        emergency_contact_number = normalise_phone(raw.get("emergency_contact_number", "")),
        nearest_hospital         = _s(raw.get("nearest_hospital", "")),
        transport_mode           = _s(raw.get("transport_mode")),
        hostel                   = _s(raw.get("hostel")),
        # Education / Skills / Projects / Experience
        education  = edu_entries,
        skills     = [_s(s) for s in raw.get("skills", []) if _s(s)],
        projects   = [_s(p) for p in raw.get("projects", []) if _s(p)],
        experience = exp_entries,
    )