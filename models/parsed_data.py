"""
models/parsed_data.py
=====================
Pydantic schemas for every structured field the extractor produces.
All fields are Optional so partial documents don't crash the pipeline.
"""

from typing import Optional
from pydantic import BaseModel, field_validator
import re


# ─────────────────────────────────────────────────────────────
#  Sub-models
# ─────────────────────────────────────────────────────────────

class NameData(BaseModel):
    full:   Optional[str] = ""
    first:  Optional[str] = ""
    middle: Optional[str] = ""
    last:   Optional[str] = ""


class DOBData(BaseModel):
    raw:         Optional[str] = ""
    dd_mm_yyyy:  Optional[str] = ""   # 14-04-2000
    dd_slash:    Optional[str] = ""   # 14/04/2000
    mm_slash:    Optional[str] = ""   # 04/14/2000
    yyyy_mm_dd:  Optional[str] = ""   # 2000-04-14
    age:         Optional[str] = ""


class AddressData(BaseModel):
    full:     Optional[str] = ""
    house_no: Optional[str] = ""
    street:   Optional[str] = ""
    city:     Optional[str] = ""
    mandal:   Optional[str] = ""
    district: Optional[str] = ""
    state:    Optional[str] = ""
    country:  Optional[str] = ""
    pincode:  Optional[str] = ""

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: str) -> str:
        """Accept only exactly 6 digits."""
        if v:
            digits = re.sub(r"\D", "", v)
            return digits if len(digits) == 6 else ""
        return ""


class EducationEntry(BaseModel):
    degree:      Optional[str] = ""
    institution: Optional[str] = ""
    year:        Optional[str] = ""
    grade:       Optional[str] = ""
    raw:         Optional[str] = ""   # fallback if structured parse fails


class ExperienceEntry(BaseModel):
    role:        Optional[str] = ""
    company:     Optional[str] = ""
    duration:    Optional[str] = ""
    description: list[str] = []


# ─────────────────────────────────────────────────────────────
#  Root output model
# ─────────────────────────────────────────────────────────────

class ParsedResume(BaseModel):
    # Personal
    name:             NameData           = NameData()
    gender:           Optional[str]      = ""
    blood_group:      Optional[str]      = ""
    dob:              DOBData            = DOBData()
    nationality:      Optional[str]      = ""
    mother_tongue:    Optional[str]      = ""
    religion:         Optional[str]      = ""
    caste_category:   Optional[str]      = ""
    aadhar:           Optional[str]      = ""   # 12 raw digits

    # Contact
    email:            Optional[str]      = ""
    phone:            Optional[str]      = ""   # digits only

    # Academic
    class_:           Optional[str]      = ""   # 'class' is a Python keyword
    section:          Optional[str]      = ""
    admission_number: Optional[str]      = ""
    academic_year:    Optional[str]      = ""
    medium:           Optional[str]      = ""
    date_of_admission:Optional[str]      = ""
    previous_school:  Optional[str]      = ""
    tc_number:        Optional[str]      = ""

    # Parent / Guardian
    father_name:       Optional[str]     = ""
    father_mobile:     Optional[str]     = ""
    father_occupation: Optional[str]     = ""
    mother_name:       Optional[str]     = ""
    mother_mobile:     Optional[str]     = ""
    mother_occupation: Optional[str]     = ""
    guardian_email:    Optional[str]     = ""

    # Address
    address:          AddressData        = AddressData()

    # Health / Emergency / Transport
    allergies:                Optional[str] = ""
    medical_conditions:       Optional[str] = ""
    emergency_contact_name:   Optional[str] = ""
    emergency_contact_number: Optional[str] = ""
    nearest_hospital:         Optional[str] = ""
    transport_mode:           Optional[str] = ""
    bus_route:                Optional[str] = ""
    hostel:                   Optional[str] = ""

    # Education / Skills / Projects / Experience
    education:  list[EducationEntry]  = []
    skills:     list[str]             = []
    projects:   list[str]             = []
    experience: list[ExperienceEntry] = []

    model_config = {"populate_by_name": True}