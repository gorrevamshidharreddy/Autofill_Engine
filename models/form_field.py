"""
models/form_field.py
====================
Schema for a single form field detected from the UI.
The matcher maps each FormField to a value from ParsedResume.
"""

from typing import Optional, Literal
from pydantic import BaseModel


FieldType = Literal[
    "text", "email", "tel", "number", "date",
    "select", "textarea", "checkbox", "radio", "hidden"
]


class FormField(BaseModel):
    """
    Represents one input/select/textarea on a web form.

    Attributes
    ----------
    label       : visible label text (e.g. "First Name *")
    name        : HTML name attribute (e.g. "firstName")
    id          : HTML id attribute
    field_type  : input type
    placeholder : placeholder text (extra matching signal)
    value       : current value in the field (may be pre-filled)
    selector    : CSS selector for the element (used by filler)
    options     : dropdown options (for select fields)
    """
    label:       Optional[str]       = ""
    name:        Optional[str]       = ""
    id:          Optional[str]       = ""
    field_type:  FieldType           = "text"
    placeholder: Optional[str]       = ""
    value:       Optional[str]       = ""
    selector:    Optional[str]       = ""
    options:     list[str]           = []

    @property
    def all_hints(self) -> str:
        """
        Concatenated lower-case string of every hint about what this
        field expects. Used by the matcher for a single fuzzy search.
        """
        parts = [
            self.label or "",
            self.name or "",
            self.id or "",
            self.placeholder or "",
        ]
        return " ".join(p for p in parts if p).lower()


class FilledField(BaseModel):
    """A FormField paired with the resolved fill value."""
    field:          FormField
    matched_key:    Optional[str] = ""   # canonical key from autofill payload
    fill_value:     Optional[str] = ""   # final formatted string to inject
    confidence:     float         = 0.0  # 0–1, from fuzzy matcher
    skipped:        bool          = False
    skip_reason:    Optional[str] = ""