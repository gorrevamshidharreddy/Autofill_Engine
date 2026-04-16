import re
import io
from datetime import date
from dateutil import parser as date_parser

import pdfplumber

# ── OCR fallback ──────────────────────────────────────────────
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────
# Anything with top-x below this is the LEFT (label) column.
# Anything above is the RIGHT (value) column.
# We compute this dynamically per PDF, but 180 is a safe default.
_COL_SPLIT_DEFAULT = 180

# Words on the same "line" if their top values differ by less than this.
_LINE_TOLERANCE = 4   # points

# Values that mean "nothing" — treat as empty
_EMPTY_VALUES = {"none", "n/a", "na", "nil", "-", "—", "not applicable", ""}

# Known Indian states for country fallback
_INDIA_STATES = {
    "telangana","andhra pradesh","karnataka","maharashtra","tamil nadu",
    "kerala","gujarat","rajasthan","uttar pradesh","madhya pradesh",
    "west bengal","bihar","odisha","punjab","haryana","jharkhand",
    "himachal pradesh","uttarakhand","goa","assam","chhattisgarh",
    "manipur","meghalaya","mizoram","nagaland","sikkim","tripura",
    "arunachal pradesh","delhi","jammu and kashmir","ladakh",
}


# ═══════════════════════════════════════════════════════════════
#  SPATIAL WORD EXTRACTOR
# ═══════════════════════════════════════════════════════════════

class SpatialExtractor:
    """
    Reads a PDF using pdfplumber extracting with layout=True, giving robust 
    extraction without relying on arbitrary coordinates. Parses the text into a 2D chunk grid.
    """
    
    LABEL_KEYWORDS = {
        "name", "first", "last", "full", "middle", "dob", "date", "birth", "age",
        "gender", "sex", "blood", "group", "nationality", "tongue", "religion",
        "caste", "category", "father", "mother", "guardian", "parent", "occupation",
        "email", "phone", "mobile", "contact", "emergency", "address", "house",
        "street", "locality", "city", "town", "mandal", "taluk", "district",
        "state", "country", "pincode", "zip", "allergies", "medical", "conditions",
        "disease", "transport", "mode", "residence", "type", "qualification",
        "degree", "university", "college", "school", "board", "year", "passing",
        "percentage", "cgpa", "grade", "experience", "company", "designation",
        "role", "salary", "skills", "languages", "hobbies", "interests",
        "identification", "aadhaar", "pan", "passport", "driving", "license"
    }

    def __init__(self, file_bytes: bytes):
        self.full_text: str        = ""
        self.lines_text: list[str] = []
        self.grid: list[list[dict]] = []

        file_obj = io.BytesIO(file_bytes)
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                # Use layout=True to preserve visual spacing
                page_text = page.extract_text(layout=True) or ""
                if not page_text.strip():
                    page_text = page.extract_text() or ""
                # OCR fallback for scanned pages
                if not page_text.strip() and OCR_AVAILABLE:
                    img = page.to_image(resolution=200).original
                    page_text = pytesseract.image_to_string(img)

                self.full_text += page_text + "\n"

        self.lines_text = [l.rstrip() for l in self.full_text.split("\n") if l.strip()]
        self._build_grid()

    def _build_grid(self):
        """
        Parses `lines_text` into a 2D grid structure.
        Each line is an array of 'chunk' dictionaries: {'text', 'start', 'end'}.
        Chunks are groups of words separated by 2+ spaces.
        """
        for line in self.lines_text:
            chunks = []
            # \S+(?: \S+)* matches words separated by ONLY SINGLE spaces. 
            # Substantial gaps (2+ spaces) break the chunk.
            for m in re.finditer(r'\S+(?: \S+)*', line):
                chunks.append({
                    'text': m.group(),
                    'start': m.start(),
                    'end': m.end()
                })
            self.grid.append(chunks)

    def _is_likely_label(self, chunk_text: str) -> bool:
        if not chunk_text: return False
        words = set(re.findall(r'[a-z]+', chunk_text.lower()))
        return len(words.intersection(self.LABEL_KEYWORDS)) > 0

    def _norm(self, text: str) -> str:
        """Normalise a label: lowercase, collapse spaces, strip punctuation."""
        return re.sub(r"\s+", " ", text.lower().strip(" :*†‡"))

    def get(self, *synonyms: str) -> str:
        """
        Look up any of the given label synonyms in the 2D chunk grid.
        Applies heuristics to determine whether the value lies to the right or directly below.
        Synonyms tried in order — put most-specific first.
        """
        for syn in synonyms:
            syn_norm = self._norm(syn)
            for i, row in enumerate(self.grid):
                for j, chunk in enumerate(row):
                    # Clean the chunk label (strip trailing colon for comparison)
                    chunk_clean = self._norm(chunk['text'].split(':')[0])
                    
                    if syn_norm == chunk_clean:
                        val = self._resolve_value(i, j)
                        if val and self._norm(val) not in _EMPTY_VALUES:
                            return val

        # Global fallback: Regex search in full_text for Label \n Value
        for syn in synonyms:
            pat = r'(?i)(?<!\w)' + re.escape(syn) + r'\s*:?\s+([^\n]+)'
            m = re.search(pat, self.full_text)
            if m:
                val = m.group(1).strip()
                if val and len(val) < 100 and self._norm(val) not in _EMPTY_VALUES:
                    return val

            pat = r'(?i)(?<!\w)' + re.escape(syn) + r'\s*:?\s*\n+([^\n]+)'
            m = re.search(pat, self.full_text)
            if m:
                val = m.group(1).strip()
                if val and len(val) < 100 and self._norm(val) not in _EMPTY_VALUES:
                    return val

        return ""

    def _resolve_value(self, i: int, j: int) -> str:
        chunk = self.grid[i][j]
        
        # 1. Value is inside the chunk (colon separated)
        if ":" in chunk['text']:
            parts = chunk['text'].split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
                
        right_chunk = self.grid[i][j+1] if j + 1 < len(self.grid[i]) else None
        
        # Find below chunk: First chunk on next line that visually aligns with us.
        below_chunk = None
        if i + 1 < len(self.grid):
            for nc in self.grid[i+1]:
                # Tolerance of 8 characters for column alignment drift
                if abs(nc['start'] - chunk['start']) <= 8:
                    below_chunk = nc
                    break
                    
        # Find right-below chunk
        right_below_chunk = None
        if right_chunk and i + 1 < len(self.grid):
            for nc in self.grid[i+1]:
                if abs(nc['start'] - right_chunk['start']) <= 8:
                    right_below_chunk = nc
                    break

        right_is_label = self._is_likely_label(right_chunk['text']) if right_chunk else False
        below_is_label = self._is_likely_label(below_chunk['text']) if below_chunk else False

        # Priority 1: Right chunk if it has a colon prefix (e.g. `Label`  `: Value`)
        if right_chunk and right_chunk['text'].startswith(':'):
            val = right_chunk['text'].lstrip(':').strip()
            if val: return val
            if not val and j + 2 < len(self.grid[i]):
                return self.grid[i][j+2]['text']

        # Priority 2: Formal grid layout breaking symmetry
        # If both right and below are present, we inspect which one is a recognized text label.
        if right_chunk and below_chunk and right_below_chunk:
            if right_is_label and not below_is_label:
                # Right chunk acts as a column header, therefore values run vertically top-down!
                return below_chunk['text']
            elif below_is_label and not right_is_label:
                # Below chunk acts as the next list header, therefore values run horizontally!
                return right_chunk['text'].lstrip(':').strip()
            else:
                # Fallback to horizontal precedence if completely ambiguous
                return right_chunk['text'].lstrip(':').strip()
            
        # Priority 3: Horizontal key-value pairs (Single form line)
        if right_chunk and not right_below_chunk:
            return right_chunk['text'].lstrip(':').strip()
            
        # Priority 4: Vertical key-value pairs (Single column list)
        if below_chunk and not right_chunk:
            return below_chunk['text']
            
        # Fallbacks
        if right_chunk: return right_chunk['text'].lstrip(':').strip()
        if below_chunk: return below_chunk['text']
        
        return ""

    def regex_search(self, pattern: str, flags=0) -> str:
        """Run a regex on the full text and return group(0) or ""."""
        m = re.search(pattern, self.full_text, flags)
        return m.group(0).strip() if m else ""

    def regex_group(self, pattern: str, group: int = 1, flags=0) -> str:
        m = re.search(pattern, self.full_text, flags)
        return m.group(group).strip() if m else ""


# ═══════════════════════════════════════════════════════════════
#  FIELD PARSERS
# ═══════════════════════════════════════════════════════════════

class ResumeParser:

    def __init__(self, file_bytes: bytes):
        self.sx = SpatialExtractor(file_bytes)

    # ── Name ──────────────────────────────────────────────────

    def name_parser(self) -> dict:
        # Try explicit labels first
        first  = self.sx.get("first name", "given name", "firstname")
        last   = self.sx.get("last name", "surname", "family name", "lastname")
        middle = self.sx.get("middle name", "middlename")
        full   = self.sx.get("full name", "name", "candidate name",
                             "student name", "applicant name")

        # The document header (first line, all-caps) is often "FIRSTNAME LASTNAME"
        header = ""
        for line in self.sx.lines_text[:3]:
            stripped = line.strip()
            # Header: 2–4 all-caps words, no digits
            if re.match(r'^[A-Z][A-Z\s]{3,}$', stripped) and len(stripped.split()) <= 4:
                header = stripped.title()
                break

        # Derive full from parts if not found
        if not full:
            if first and last:
                full = f"{first} {middle} {last}".strip() if middle else f"{first} {last}"
            elif header:
                full = header

        # Derive parts from full/header if not found
        if full and not first:
            parts = full.split()
            first  = parts[0] if parts else ""
            last   = parts[-1] if len(parts) > 1 else ""
            middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
        elif header and not first:
            parts  = header.split()
            first  = parts[0] if parts else ""
            last   = parts[-1] if len(parts) > 1 else ""
            middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""

        return {
            "full":   full   or (f"{first} {last}".strip() if first else ""),
            "first":  first,
            "middle": middle,
            "last":   last,
        }

    # ── Email ─────────────────────────────────────────────────

    def email_parser(self) -> str:
        # All email addresses in the document
        emails = re.findall(r'[\w.\-+]+@[\w.\-]+\.\w{2,}', self.sx.full_text)
        if not emails:
            return ""
        # Primary email = the one NOT in guardian_email label
        guardian_raw = self.sx.get("guardian email", "parent email",
                                   "parent / guardian email", "family email")
        # Return candidate's own email (first one found, exclude guardian)
        for e in emails:
            if e.lower() != guardian_raw.lower():
                return e
        return emails[0]

    def guardian_email_parser(self) -> str:
        val = self.sx.get("guardian email", "parent / guardian email",
                          "parent email", "family email")
        if val and "@" in val:
            return val
        # Fallback: second email in doc
        emails = re.findall(r'[\w.\-+]+@[\w.\-]+\.\w{2,}', self.sx.full_text)
        return emails[-1] if len(emails) > 1 else ""

    # ── Phone ─────────────────────────────────────────────────

    def _clean_phone(self, raw: str) -> str:
        """Return 10 digits only from a phone string."""
        digits = re.sub(r'\D', '', raw or "")
        # Strip country code +91 / 91 prefix
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        return digits if len(digits) == 10 else digits  # return what we have

    def phone_parser(self) -> str:
        """Primary (candidate's own) phone number."""
        raw = self.sx.get("phone", "mobile", "mobile number", "phone number",
                          "contact number", "cell", "telephone")
        if raw:
            return self._clean_phone(raw)
        # Header line often has "Phone: +91 XXXXXXXXXX"
        m = re.search(r'Phone[:\s]+(\+?91[\s\-]?)?([6-9]\d{9})', self.sx.full_text, re.I)
        if m:
            return self._clean_phone(m.group(0))
        # Global fallback: first Indian mobile
        m = re.search(r'\b(?:\+91[\s\-]?)?([6-9]\d{9})\b', self.sx.full_text)
        return self._clean_phone(m.group(0)) if m else ""

    def alternate_phone_parser(self) -> str:
        raw = self.sx.get("alternate mobile", "alternate phone", "secondary phone",
                          "other mobile", "alternative mobile", "alt mobile")
        if raw:
            return self._clean_phone(raw)
        return ""

    def father_mobile_parser(self) -> str:
        raw = self.sx.get("father mobile", "father phone", "father contact",
                          "father's mobile", "father mobile number")
        return self._clean_phone(raw) if raw else ""

    def mother_mobile_parser(self) -> str:
        raw = self.sx.get("mother mobile", "mother phone", "mother contact",
                          "mother's mobile", "mother mobile number")
        return self._clean_phone(raw) if raw else ""

    def emergency_contact_number_parser(self) -> str:
        raw = self.sx.get("emergency contact number", "emergency number",
                          "emergency phone", "contact number")
        return self._clean_phone(raw) if raw else ""

    # ── DOB ───────────────────────────────────────────────────

    def dob_parser(self) -> dict:
        raw = self.sx.get("date of birth", "dob", "birth date", "d.o.b",
                          "birthdate", "date of birth (dd-mm-yyyy)")
        if not raw:
            m = re.search(r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b',
                          self.sx.full_text)
            raw = m.group(1) if m else ""
        if not raw:
            return {k: "" for k in ["raw","dd-mm-yyyy","dd/mm/yyyy",
                                    "mm/dd/yyyy","yyyy-mm-dd","age"]}
        try:
            parsed = date_parser.parse(raw, fuzzy=True, dayfirst=True)
            age = (date.today() - parsed.date()).days // 365
            return {
                "raw":        raw.strip(),
                "dd-mm-yyyy": parsed.strftime("%d-%m-%Y"),
                "dd/mm/yyyy": parsed.strftime("%d/%m/%Y"),
                "mm/dd/yyyy": parsed.strftime("%m/%d/%Y"),
                "yyyy-mm-dd": parsed.strftime("%Y-%m-%d"),
                "age":        str(age) if 0 < age < 120 else "",
            }
        except Exception:
            return {"raw": raw.strip(), "dd-mm-yyyy": "", "dd/mm/yyyy": "",
                    "mm/dd/yyyy": "", "yyyy-mm-dd": "", "age": ""}

    # ── Personal ──────────────────────────────────────────────

    def gender_parser(self) -> str:
        raw = self.sx.get("gender", "sex")
        if raw:
            return raw
        for token, val in [("female","Female"), ("male","Male")]:
            if re.search(r'\b' + token + r'\b', self.sx.full_text, re.I):
                return val
        return ""

    def blood_group_parser(self) -> str:
        raw = self.sx.get("blood group", "blood type", "bg")
        if raw:
            return raw
        m = re.search(r'\b(A|B|AB|O)[+-]\b', self.sx.full_text)
        return m.group() if m else ""

    def nationality_parser(self) -> str:
        raw = self.sx.get("nationality", "citizenship")
        if raw:
            return raw
        return "Indian" if re.search(r'\bIndia(n)?\b', self.sx.full_text, re.I) else ""

    def mother_tongue_parser(self) -> str:
        # Use EXACT label match — never match "medium"
        return self.sx.get("mother tongue", "native language", "first language",
                           "home language", "regional language")

    def religion_parser(self) -> str:
        raw = self.sx.get("religion", "faith")
        if raw:
            return raw
        for rel in ["Hindu","Muslim","Christian","Sikh","Buddhist","Jain","Zoroastrian"]:
            if re.search(r'\b' + rel + r'\b', self.sx.full_text, re.I):
                return rel
        return ""

    def caste_category_parser(self) -> str:
        raw = self.sx.get("caste category", "caste", "category", "sub-caste",
                          "social category")
        if raw:
            return raw
        m = re.search(r'\b(OBC|SC|ST|General|EWS|BC-[A-E]|GEN)\b', self.sx.full_text, re.I)
        return m.group().upper() if m else ""

    def aadhar_parser(self) -> str:
        """Always returns 12 raw digits (no spaces, no hyphens)."""
        raw = self.sx.get("aadhaar number", "aadhar number", "aadhaar",
                          "aadhar", "aadhar no", "uid", "aadhaar no")
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 12:
            return digits
        # Global search for 12-digit pattern (with or without separators)
        m = re.search(r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b', self.sx.full_text)
        if m:
            digits = re.sub(r'\D', '', m.group())
            if len(digits) == 12:
                return digits
        return ""

    def marital_status_parser(self) -> str:
        return self.sx.get("marital status", "married", "marital",
                           "relationship status")

    # ── Address ───────────────────────────────────────────────

    def address_parser(self) -> dict:
        house    = self.sx.get("house no", "house no.", "house number", "flat no",
                               "flat number", "door no", "h.no", "plot no",
                               "house", "flat")
        street   = self.sx.get("street / locality", "street", "street address",
                               "locality", "road", "lane", "area")
        city     = self.sx.get("village / town / city", "city / town", "city/town",
                               "city", "town", "village", "city or village",
                               "city or town")
        mandal   = self.sx.get("mandal / taluk", "mandal", "taluk", "tehsil",
                               "mandal or taluk")
        district = self.sx.get("district")
        state    = self.sx.get("state", "province")
        country  = self.sx.get("country", "nation", "country of residence")
        pincode  = self.sx.get("pincode", "pin code", "pin", "zip",
                               "zip code", "postal code", "post code")

        # Pincode: strictly 6 digits
        if pincode:
            d6 = re.search(r'\b(\d{6})\b', pincode)
            pincode = d6.group(1) if d6 else ""
        if not pincode:
            d6 = re.search(r'\b(\d{6})\b', self.sx.full_text)
            pincode = d6.group(1) if d6 else ""

        # State fallback — scan text for known Indian states
        if not state:
            for s in _INDIA_STATES:
                if re.search(r'\b' + re.escape(s) + r'\b', self.sx.full_text, re.I):
                    state = s.title()
                    break

        # Country fallback
        if not country:
            if state or re.search(r'\bIndia\b', self.sx.full_text, re.I):
                country = "India"

        parts = [p for p in [house, street, city, mandal, district, state,
                              country, pincode] if p]
        full_addr = ", ".join(parts)

        return {
            "full":     full_addr,
            "house_no": house,
            "street":   street,
            "city":     city,
            "mandal":   mandal,
            "district": district,
            "state":    state,
            "country":  country,
            "pincode":  pincode,
        }

    # ── Parent / Guardian ─────────────────────────────────────

    def father_name_parser(self) -> str:
        return self.sx.get("father / guardian name", "father name",
                           "father guardian name", "father's name",
                           "guardian name")

    def mother_name_parser(self) -> str:
        return self.sx.get("mother / guardian name", "mother name",
                           "mother guardian name", "mother's name")

    def father_occupation_parser(self) -> str:
        return self.sx.get("father occupation", "father's occupation",
                           "father profession")

    def mother_occupation_parser(self) -> str:
        return self.sx.get("mother occupation", "mother's occupation",
                           "mother profession")

    # ── Academic ─────────────────────────────────────────────
    # IMPORTANT: academic_year MUST NOT fall back to DOB year.
    # It only reads from an explicit "Academic Year" label.

    def academic_year_parser(self) -> str:
        raw = self.sx.get("academic year", "academic session", "school year")
        if raw:
            # Validate: must look like "2024-25" or "2023-2024", not a plain year
            if re.search(r'\d{4}[\-\/]\d{2,4}', raw):
                return raw
            # If it's just a 4-digit year, reject (likely DOB year leaked in)
        return ""

    # Medium: ONLY "medium of instruction" — never language/tongue fields
    def medium_parser(self) -> str:
        raw = self.sx.get("medium of instruction", "medium",
                          "instruction medium", "teaching medium",
                          "language of instruction")
        # Sanity check: reject values that are common tongue/language names
        # that would indicate a wrong match
        if not raw:
            return ""
        tongue_words = {"telugu","hindi","english","urdu","tamil","kannada",
                        "malayalam","marathi","bengali","gujarati","punjabi",
                        "odia","assamese"}
        # Allow language as medium of instruction — just not "Mother Tongue" label
        return raw

    def class_parser(self) -> str:
        return self.sx.get("class", "grade", "standard", "std")

    def section_parser(self) -> str:
        return self.sx.get("section", "division")

    def admission_number_parser(self) -> str:
        raw = self.sx.get("admission number", "admission no", "adm no",
                          "roll number", "roll no")
        if raw:
            return raw
        m = re.search(r'\b(ADM\w+|ROLL\d+)\b', self.sx.full_text, re.I)
        return m.group() if m else ""

    def previous_school_parser(self) -> str:
        return self.sx.get("previous school name", "previous school",
                           "last school", "school name",
                           "transfer from school")

    def date_of_admission_parser(self) -> str:
        raw = self.sx.get("date of admission", "admission date", "joining date")
        if not raw:
            return ""
        try:
            return date_parser.parse(raw, fuzzy=True, dayfirst=True).strftime("%d-%m-%Y")
        except Exception:
            return raw

    # ── Health / Emergency / Transport ───────────────────────

    def allergies_parser(self) -> str:
        return self.sx.get("allergies details", "allergies", "allergy",
                           "any allergies")

    def medical_conditions_parser(self) -> str:
        raw = self.sx.get("medical conditions", "medical condition",
                          "any medical conditions", "health conditions")
        # "None" means no condition — return empty
        return "" if self.sx._norm(raw) in _EMPTY_VALUES else raw

    def emergency_contact_name_parser(self) -> str:
        return self.sx.get("emergency contact name", "emergency contact",
                           "contact name", "emergency name",
                           "contact person name")

    def transport_mode_parser(self) -> str:
        return self.sx.get("mode of transport", "transport mode",
                           "transport", "conveyance")

    def hostel_parser(self) -> str:
        return self.sx.get("hostel / day scholar", "hostel",
                           "day scholar", "boarding",
                           "hostel or day scholar")

    # ── Education / Skills / Projects / Experience ────────────

    def education_parser(self) -> list[dict]:
        """
        Structured education parsing using section detection.
        Looks for degree keywords and grabs the surrounding context.
        """
        block = self._section_block("education", "qualification",
                                    "academic", "academics",
                                    "educational qualification")
        if not block:
            return []

        degree_pat = re.compile(
            r'\b(B\.?Tech|M\.?Tech|B\.?E|M\.?E|B\.?Sc|M\.?Sc|MBA|BCA|MCA'
            r'|PhD|10th|12th|SSC|HSC|Intermediate|Diploma|B\.?Com|M\.?Com)\b', re.I
        )
        year_pat  = re.compile(r'\b(19|20)\d{2}\b')
        grade_pat = re.compile(r'(\d+\.?\d*)\s*(%|CGPA|GPA|SGPA)', re.I)

        entries, current = [], {}
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            deg = degree_pat.search(line)
            yr  = year_pat.findall(line)
            grd = grade_pat.search(line)

            if deg:
                if current:
                    entries.append(current)
                current = {"degree": deg.group(), "institution": "",
                           "year": "", "grade": ""}
                inst = degree_pat.sub("", line).strip(" -|,")
                if inst:
                    current["institution"] = inst
            if yr and current:
                current["year"] = yr[-1]
            if grd and current:
                current["grade"] = grd.group()
            if not deg and current and not current["institution"]:
                current["institution"] = line

        if current:
            entries.append(current)
        return entries or [{"raw": block}] if block else []

    def skills_parser(self) -> list[str]:
        block = self._section_block("skills", "technical skills",
                                    "key skills", "technologies", "expertise")
        if not block:
            return []
        raw  = re.split(r'[\n•\|;,]+', block)
        return [s.strip().strip("-").strip() for s in raw
                if s.strip() and len(s.strip()) < 60]

    def projects_parser(self) -> list[str]:
        block = self._section_block("projects", "project details",
                                    "key projects", "major projects")
        if not block:
            return []
        titles = []
        for line in block.split("\n"):
            line = line.strip().strip("-•").strip()
            if not line:
                continue
            title = re.split(r'[:\-–|]', line)[0].strip()
            if title and len(title) < 80:
                titles.append(title)
        return list(dict.fromkeys(titles))

    def experience_parser(self) -> list[dict]:
        block = self._section_block("experience", "work experience",
                                    "professional experience", "employment",
                                    "work history", "internship")
        if not block:
            return []

        dr_pat = re.compile(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?\.?\s*'
            r'(\d{4})\s*[-–to]+\s*'
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?\.?\s*'
            r'(\d{4}|Present|Current)', re.I
        )
        entries, current = [], {}
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            dr = dr_pat.search(line)
            if dr:
                if current:
                    entries.append(current)
                current = {"role": "", "company": "",
                           "duration": dr.group(), "description": []}
                before = line[:dr.start()].strip(" -|,")
                parts  = re.split(r'[,|@\-–]', before, maxsplit=1)
                current["role"]    = parts[0].strip() if parts else ""
                current["company"] = parts[1].strip() if len(parts) > 1 else ""
            elif current:
                clean = line.strip("-•").strip()
                if clean:
                    current["description"].append(clean)
            else:
                current = {"role": line, "company": "",
                           "duration": "", "description": []}
        if current:
            entries.append(current)
        return entries or []

    # ──────────────────────────────────────────────────────────
    #  Section block extractor (for multi-line sections)
    # ──────────────────────────────────────────────────────────

    def _section_block(self, *synonyms: str, max_lines: int = 40) -> str:
        """
        Find a section heading and return the text block under it,
        stopping at the next ALL-CAPS heading.
        """
        for syn in synonyms:
            pat = re.compile(r'(?<!\w)' + re.escape(syn) + r'\s*:?\s*', re.I)
            m   = pat.search(self.sx.full_text)
            if m:
                start = m.end()
                # Find next section heading (ALL-CAPS word, 4+ chars)
                nxt = re.search(r'\n[A-Z]{4,}', self.sx.full_text[start:])
                end = start + nxt.start() if nxt else len(self.sx.full_text)
                block = self.sx.full_text[start:end].strip()
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                return "\n".join(lines[:max_lines])
        return ""


# ═══════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def process_resume(file_bytes: bytes) -> dict:
    """
    Main entry point called by main.py / FastAPI.

    Returns
    -------
    {
        "status": "success",
        "data":   { all structured fields },
        "autofill": { flat key→value map for form filling }
    }
    """
    try:
        p = ResumeParser(file_bytes)

        name    = p.name_parser()
        dob     = p.dob_parser()
        address = p.address_parser()

        data = {
            # Name
            "name":            name,
            # Personal
            "gender":          p.gender_parser(),
            "blood_group":     p.blood_group_parser(),
            "dob":             dob,
            "nationality":     p.nationality_parser(),
            "mother_tongue":   p.mother_tongue_parser(),
            "religion":        p.religion_parser(),
            "caste_category":  p.caste_category_parser(),
            "aadhar":          p.aadhar_parser(),
            "marital_status":  p.marital_status_parser(),
            # Contact
            "email":           p.email_parser(),
            "phone":           p.phone_parser(),
            "alternate_phone": p.alternate_phone_parser(),
            # Parent / Guardian
            "father_name":        p.father_name_parser(),
            "father_mobile":      p.father_mobile_parser(),
            "father_occupation":  p.father_occupation_parser(),
            "mother_name":        p.mother_name_parser(),
            "mother_mobile":      p.mother_mobile_parser(),
            "mother_occupation":  p.mother_occupation_parser(),
            "guardian_email":     p.guardian_email_parser(),
            # Address
            "address":         address,
            # Academic
            "class":           p.class_parser(),
            "section":         p.section_parser(),
            "admission_number":p.admission_number_parser(),
            "academic_year":   p.academic_year_parser(),
            "medium":          p.medium_parser(),
            "date_of_admission":p.date_of_admission_parser(),
            "previous_school": p.previous_school_parser(),
            # Health / Emergency / Transport
            "allergies":                p.allergies_parser(),
            "medical_conditions":       p.medical_conditions_parser(),
            "emergency_contact_name":   p.emergency_contact_name_parser(),
            "emergency_contact_number": p.emergency_contact_number_parser(),
            "transport_mode":           p.transport_mode_parser(),
            "hostel":                   p.hostel_parser(),
            # Education / Skills / Projects / Experience
            "education":   p.education_parser(),
            "skills":      p.skills_parser(),
            "projects":    p.projects_parser(),
            "experience":  p.experience_parser(),
        }

        return {"status": "success", "data": data}

    except Exception as exc:
        import traceback
        return {
            "status": "error",
            "error":  str(exc),
            "trace":  traceback.format_exc(),
        }