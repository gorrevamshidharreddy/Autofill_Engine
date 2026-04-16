from models.parsed_data import ParsedResume
from models.form_field  import FormField, FilledField
from utils.text_utils   import (
    multi_signal_score, THRESHOLD_SKIP,
)
from utils.date_utils   import detect_date_format_from_placeholder, format_date


# ─────────────────────────────────────────────────────────────
#  SYNONYM REGISTRY
#  IMPORTANT ordering rules:
#  • More-specific keys must appear BEFORE generic ones in the
#    scoring loop so specificity wins ties.
#  • "medium" must NOT contain language/tongue words.
#  • "academic_year" must NOT contain bare "year".
# ─────────────────────────────────────────────────────────────
FIELD_SYNONYMS: dict[str, list[str]] = {

    # ── Name ──────────────────────────────────────────────────
    "full_name":   ["full name", "student name", "candidate name",
                    "applicant name", "name"],
    "first_name":  ["first name", "given name", "firstname", "first"],
    "middle_name": ["middle name", "middlename"],
    "last_name":   ["last name", "surname", "family name", "lastname"],

    # ── Personal ──────────────────────────────────────────────
    "gender":         ["gender", "sex"],
    "blood_group":    ["blood group", "blood type", "bg"],

    # DOB — date-like synonyms only, never bare "year"
    "dob":            ["date of birth", "dob", "birth date", "d.o.b",
                       "birthdate", "date of birth dd-mm-yyyy",
                       "date of birth (dd-mm-yyyy)"],
    "age":            ["age", "age auto-calculated", "age in years",
                       "age (auto-calculated)"],

    "nationality":    ["nationality", "citizenship"],

    # Mother tongue — all language-identity labels go HERE, not in medium
    "mother_tongue":  ["mother tongue", "native language", "first language",
                       "language", "regional language", "home language",
                       "spoken language"],

    "email":          ["email", "e-mail", "email address", "mail",
                       "email id", "email-id"],
    "religion":       ["religion", "faith"],
    "marital_status": ["marital status", "married", "marital",      # ★ new
                       "relationship status"],
    "aadhar":         ["aadhaar number", "aadhar number", "aadhaar",
                       "aadhar", "aadhar no", "uid", "12-digit aadhaar",
                       "aadhaar no"],
    "caste_category": ["caste category", "caste", "category", "sub-caste",
                       "social category"],

    # ── Contact ───────────────────────────────────────────────
    "phone":           ["mobile number", "phone number", "mobile",
                        "phone", "contact number", "cell",
                        "telephone", "10-digit mobile"],
    "alternate_phone": ["alternate mobile", "alternate phone",          # ★ new
                        "secondary phone", "other mobile",
                        "alternative mobile", "alt mobile",
                        "alternate number"],

    # ── Parent / Guardian ─────────────────────────────────────
    "father_name":       ["father name", "father / guardian name",
                          "father guardian name", "guardian name",
                          "father's name"],
    "father_mobile":     ["father mobile", "father phone",
                          "father contact", "father's mobile",
                          "father mobile number"],
    "father_occupation": ["father occupation", "father's occupation",
                          "father profession"],
    "mother_name":       ["mother name", "mother / guardian name",
                          "mother guardian name", "mother's name"],
    "mother_mobile":     ["mother mobile", "mother phone",
                          "mother contact", "mother's mobile",
                          "mother mobile number"],
    "mother_occupation": ["mother occupation", "mother's occupation",
                          "mother profession"],
    "guardian_email":    ["parent / guardian email", "parent email",
                          "guardian email", "family email",
                          "parent guardian email"],

    # ── Emergency Contact ─────────────────────────────────────
    "emergency_contact_name":   ["emergency contact name",
                                  "emergency contact",
                                  "emergency name",
                                  "contact name",              # ★ new alias
                                  "contact person name"],
    "emergency_contact_number": ["emergency contact number",
                                  "emergency number",
                                  "emergency phone",
                                  "contact number",            # careful — scored against phone too
                                  "10-digit number"],
    "relationship":      ["relationship", "relation",           # ★ new
                          "relation with student",
                          "relationship to student",
                          "relation with patient"],

    # ── Address ───────────────────────────────────────────────
    "address":   ["address", "residential address", "current address",
                  "permanent address", "mailing address"],
    "house_no":  ["house no", "house no.", "house number", "flat no",
                  "door no", "h.no", "plot no"],
    "street":    ["street", "street / locality", "street address",
                  "road", "lane", "area", "locality",
                  "street or locality"],
    "city":      ["village / town / city", "city / town", "city/town",
                  "city", "town", "village", "city or village",
                  "city or town", "village town city"],
    "mandal":    ["mandal / taluk", "mandal", "taluk", "tehsil",
                  "mandal or taluk", "mandal/taluk"],
    "district":  ["district"],
    "state":     ["state", "province"],
    "country":   ["country", "nation", "country of residence",
                  "country of birth", "citizenship country"],
    "pincode":   ["pincode", "pin code", "pin", "zip", "zip code",
                  "postal code", "post code", "6-digit pin code"],

    # ── Branch / Institution ──────────────────────────────────
    "branch_id": ["branch id", "branch code", "branch",         # ★ new
                  "branch number"],

    # ── Academic ──────────────────────────────────────────────
    "class_":            ["class", "grade", "standard", "std"],
    "section":           ["section", "division"],
    "admission_number":  ["admission number", "admission no",
                          "adm no", "roll number", "roll no"],

    # FIXED: "academic_year" must contain "academic" — never bare "year"
    "academic_year":     ["academic year", "academic session",
                          "school year", "financial year"],

    # FIXED: "medium" must NOT contain language/tongue words
    "medium":            ["medium of instruction", "medium",
                          "instruction medium", "teaching medium",
                          "language of instruction"],

    "date_of_admission": ["date of admission", "admission date",
                          "joining date", "date of joining"],
    "previous_school":   ["previous school name", "previous school",
                          "last school", "school name",
                          "transfer from school"],
    "tc_number":         ["transfer certificate", "tc number", "tc no"],

    # ── Education / Skills / Projects / Experience ────────────
    "education":  ["education", "qualification", "academic qualification",
                   "educational details"],
    "skills":     ["skills", "technical skills", "key skills",
                   "technologies", "expertise"],
    "projects":   ["projects", "project details", "key projects"],
    "experience": ["experience", "work experience",
                   "professional experience", "internship"],

    # ── Health / Emergency / Transport ────────────────────────
    "allergies":          ["allergies details", "allergies", "allergy",
                           "any allergies"],
    "medical_conditions": ["medical conditions", "medical condition",
                           "any medical conditions", "health conditions"],
    "nearest_hospital":   ["nearest hospital / doctor", "nearest hospital",
                           "hospital", "doctor name",
                           "hospital or doctor name"],
    "transport_mode":     ["mode of transport", "transport mode",
                           "transport", "conveyance"],
    "bus_route":          ["bus route / vehicle number", "bus route",
                           "vehicle number", "route number",
                           "bus route or vehicle no"],
    "hostel":             ["hostel / day scholar", "hostel",
                           "day scholar", "boarding",
                           "hostel or day scholar"],

    # ── Universal / Professional ★ new ────────────────────────
    "website":          ["website", "personal website", "portfolio url",
                         "blog", "web address"],
    "linkedin":         ["linkedin", "linkedin profile", "linkedin url"],
    "pan_number":       ["pan number", "pan no", "pan card",
                         "permanent account number"],
    "passport_number":  ["passport number", "passport no", "passport"],
    "voter_id":         ["voter id", "voter id number",
                         "epic number", "voter card"],
    "driving_license":  ["driving license", "driving licence",
                         "dl number", "license number"],
    "employee_id":      ["employee id", "emp id", "staff id",
                         "employee number", "employee code"],
    "department":       ["department", "dept"],
    "designation":      ["designation", "job title", "position",
                         "role", "post", "title"],
    "annual_income":    ["annual income", "yearly income", "income",
                         "family income", "annual salary"],
    "bank_account":     ["bank account number", "account number",
                         "bank account no"],
    "ifsc_code":        ["ifsc code", "ifsc", "bank ifsc",
                         "ifsc number"],
}


# ─────────────────────────────────────────────────────────────
#  Autofill payload builder
# ─────────────────────────────────────────────────────────────

def build_payload(resume: ParsedResume) -> dict[str, str]:
    n   = resume.name
    dob = resume.dob
    adr = resume.address

    edu_str = "; ".join(
        f"{e.degree} {e.institution} {e.year}".strip()
        for e in resume.education if e.degree or e.institution
    )
    exp_str = "; ".join(
        (e.role + (" at " + e.company if e.company else "")).strip()
        for e in resume.experience if e.role
    )

    return {
        # Name
        "full_name":   n.full,
        "first_name":  n.first,
        "middle_name": n.middle,
        "last_name":   n.last,
        # Personal
        "gender":         resume.gender,
        "blood_group":    resume.blood_group,
        "dob":            dob.dd_mm_yyyy,
        "age":            dob.age,
        "nationality":    resume.nationality,
        "mother_tongue":  resume.mother_tongue,
        "email":          resume.email,
        "religion":       resume.religion,
        "marital_status": getattr(resume, "marital_status", ""),
        "aadhar":         resume.aadhar,
        "caste_category": resume.caste_category,
        # Contact
        "phone":           resume.phone,
        "alternate_phone": getattr(resume, "alternate_phone", ""),
        # Parent / Guardian
        "father_name":       resume.father_name,
        "father_mobile":     resume.father_mobile,
        "father_occupation": resume.father_occupation,
        "mother_name":       resume.mother_name,
        "mother_mobile":     resume.mother_mobile,
        "mother_occupation": resume.mother_occupation,
        "guardian_email":    resume.guardian_email or resume.email,
        # Emergency
        "emergency_contact_name":   resume.emergency_contact_name,
        "emergency_contact_number": resume.emergency_contact_number,
        "relationship":             getattr(resume, "relationship", ""),
        # Address
        "address":   adr.full,
        "house_no":  adr.house_no,
        "street":    adr.street,
        "city":      adr.city,
        "mandal":    adr.mandal,
        "district":  adr.district,
        "state":     adr.state,
        "country":   adr.country,
        "pincode":   adr.pincode,
        # Branch
        "branch_id": "",
        # Academic
        "class_":            resume.class_,
        "section":           resume.section,
        "admission_number":  resume.admission_number,
        "academic_year":     resume.academic_year,
        "medium":            resume.medium,
        "date_of_admission": resume.date_of_admission,
        "previous_school":   resume.previous_school,
        "tc_number":         resume.tc_number,
        # Health
        "allergies":                resume.allergies,
        "medical_conditions":       resume.medical_conditions,
        "nearest_hospital":         resume.nearest_hospital,
        "transport_mode":           resume.transport_mode,
        "bus_route":                resume.bus_route,
        "hostel":                   resume.hostel,
        # Education / Skills / Projects / Experience
        "education":  edu_str,
        "skills":     ", ".join(resume.skills),
        "projects":   ", ".join(resume.projects),
        "experience": exp_str,
        # Universal / Professional (empty by default; populated if parsed)
        "website":         "",
        "linkedin":        "",
        "pan_number":      "",
        "passport_number": "",
        "voter_id":        "",
        "driving_license": "",
        "employee_id":     "",
        "department":      "",
        "designation":     "",
        "annual_income":   "",
        "bank_account":    "",
        "ifsc_code":       "",
    }


# ─────────────────────────────────────────────────────────────
#  Core matcher
# ─────────────────────────────────────────────────────────────

def match_fields(
    form_fields: list[FormField],
    resume: ParsedResume,
) -> list[FilledField]:

    payload = build_payload(resume)
    results: list[FilledField] = []

    for field in form_fields:
        hints = field.all_hints

        best_key:   str | None = None
        best_score: float      = 0.0

        for key, synonyms in FIELD_SYNONYMS.items():
            score = multi_signal_score(hints, key, synonyms)
            if score > best_score:
                best_score = score
                best_key   = key

        # Below skip threshold
        if best_score < THRESHOLD_SKIP / 100:
            results.append(FilledField(
                field       = field,
                matched_key = None,
                fill_value  = "",
                confidence  = best_score,
                skipped     = True,
                skip_reason = f"low_confidence:{best_score:.2f}",
            ))
            continue

        raw_value = payload.get(best_key, "") if best_key else ""

        # ── BLANK-IF-MISSING: never inject empty placeholder ──
        if not raw_value or not str(raw_value).strip():
            results.append(FilledField(
                field       = field,
                matched_key = best_key,
                fill_value  = "",
                confidence  = best_score,
                skipped     = True,
                skip_reason = "no_data",
            ))
            continue

        # DOB: format to match field placeholder
        if best_key == "dob" and field.placeholder:
            fmt       = detect_date_format_from_placeholder(field.placeholder)
            raw_value = format_date(resume.dob, fmt)

        results.append(FilledField(
            field       = field,
            matched_key = best_key,
            fill_value  = raw_value,
            confidence  = best_score,
            skipped     = False,
        ))

    return results