"""The patient's own details, as a bill or a lab report prints them.

Bills and lab reports print an age ("68 Yrs"), sometimes a date of birth, a
mobile number and an address. When a family scans one before saying whose it
is, these are offered as the details of the member they file it under -- the
answer to "who is this?" is usually already on the page.

What the reader transcribed is kept on the unfiled case or report exactly as
printed, and turned into a suggestion here: a date only if it is a real date
of birth, a number only if it is an Indian mobile, an email only if it is
one. Nothing is guessed. A bill that prints "Age: 68" gives an age, never a
date of birth worked back from it.

Once the scan is filed, the printed copy is dropped: what the family accepted
now lives on the member, and what they didn't has no reason to be kept.
"""

import re
from datetime import date

from pydantic import EmailStr, TypeAdapter, ValidationError

from db import india_today
from models import SuggestedMember
from phone import normalize_indian_mobile
from references import parse_bill_date

FIELDS = ("age", "dob", "phone", "email", "address")

# "68", "68 Y", "68 Yrs", "68Y 3M", "68 years". The years, and only them --
# never a baby's "6 M" or "10 days" read as years.
_AGE = re.compile(
    r"^\s*(\d{1,3})\s*(?:y|yr|yrs|year|years)?\b(?!\s*(?:m|mo|mon|month|months|d|day|days)\b)",
    re.IGNORECASE,
)
_EMAIL = TypeAdapter(EmailStr)


def printed(**fields: str) -> dict[str, str] | None:
    """What the reader transcribed, keeping only what it found. None for nothing."""
    kept = {key: value.strip() for key, value in fields.items() if key in FIELDS and value and value.strip()}
    return kept or None


def _birth_date(text: str, today: date) -> date | None:
    born = parse_bill_date(text)
    return born if born is not None and date(1900, 1, 1) <= born <= today else None


def _age(text: str) -> int | None:
    match = _AGE.match(text)
    if not match:
        return None
    years = int(match.group(1))
    return years if years <= 120 else None


def _email(text: str) -> str | None:
    try:
        return _EMAIL.validate_python(text).lower()
    except ValidationError:
        return None


def suggestion(details: dict[str, str] | None, name: str) -> SuggestedMember | None:
    """The member a family could file this under, from what the page printed.

    None where the page printed nothing worth offering, not even a name.
    """
    details = details or {}
    today = india_today()
    suggested = SuggestedMember(
        name=name.strip()[:80],
        date_of_birth=_birth_date(details.get("dob", ""), today),
        age=_age(details.get("age", "")),
        phone=normalize_indian_mobile(details.get("phone", "")),
        email=_email(details.get("email", "")),
        address=details.get("address", "").strip()[:300] or None,
    )
    return suggested if any(suggested.model_dump().values()) else None
