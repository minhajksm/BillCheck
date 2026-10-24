"""The shape the lab reader returns, and the one claim of its we check.

Forgiving in the same way `analysis.py` is: a null where text was asked for
is kept as "", and a field the reader adds is ignored. A whole report is not
worth failing over either.

The claim we check is `status`. "Within range" read by a family whose result
is not within the range printed beside it is the single worst thing this
feature could say, and it is the one thing on the page we can verify without
asking a model: where the value and the printed range are both plain
numbers, the comparison is arithmetic, and arithmetic wins. Where either is
not -- "Negative", "<0.5", "Reactive", a range that is a sentence -- the
reader's reading stands, because there is nothing better to replace it with.

A test with no printed range is "no_range" whatever the reader says. The
prompt forbids supplying a range from its own knowledge; a "low" with no
range beside it is one it supplied anyway.
"""

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from analysis import Text

logger = logging.getLogger("billcheck.lab")

Status = Literal["low", "high", "in_range", "no_range"]
STATUSES: frozenset[str] = frozenset({"low", "high", "in_range", "no_range"})


class LabHeader(BaseModel):
    lab_name: Text = ""
    patient_name: Text = ""
    report_date: Text = ""


class LabTest(BaseModel):
    """One result, verbatim, with the reader's explanation in both languages."""

    name: Text
    # Verbatim, as text: "9.8", "<0.5", "Negative" and "1+" are all results.
    value: Text = ""
    unit: Text = ""
    range: Text = ""
    status: Status = "no_range"
    explanation_en: Text = ""
    explanation_hi: Text = ""

    @field_validator("status", mode="before")
    @classmethod
    def _known_status(cls, value: Any) -> Any:
        """An unrecognised status reads as "no_range": the one that claims
        nothing, rather than a refusal or a guess at in-range."""
        return value if value in STATUSES else "no_range"


class LabAnalysis(BaseModel):
    report: LabHeader = Field(default_factory=LabHeader)
    tests: list[LabTest]
    summary_en: Text = ""
    summary_hi: Text = ""
    questions_en: list[str] = Field(default_factory=list)
    questions_hi: list[str] = Field(default_factory=list)
    # Only where the report itself marks a result critical. The prompt says
    # so; the app shows it as "show this to a doctor today" and nothing more.
    urgent: bool = False


# "12.0 - 15.0", "12-15", "12.0 – 15.0", "12 to 15"
_BETWEEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(-?\d+(?:\.\d+)?)\s*$", re.I)
# "< 200", "<=200", "≤ 5", "up to 200", "upto 200", "less than 200"
_BELOW = re.compile(r"^\s*(?:<=?|≤|up\s*to|upto|less\s+than)\s*(-?\d+(?:\.\d+)?)\s*$", re.I)
# "> 40", ">=40", "≥ 40", "more than 40", "greater than 40"
_ABOVE = re.compile(r"^\s*(?:>=?|≥|more\s+than|greater\s+than)\s*(-?\d+(?:\.\d+)?)\s*$", re.I)
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")


def _number(text: str) -> float | None:
    match = _NUMBER.match(text.replace(",", ""))
    return float(match.group(1)) if match else None


def _bounds(text: str) -> tuple[float | None, float | None] | None:
    """The printed range as (low, high), either open, or None if it isn't numbers."""
    cleaned = text.replace(",", "")
    if match := _BETWEEN.match(cleaned):
        low, high = float(match.group(1)), float(match.group(2))
        return (min(low, high), max(low, high))
    if match := _BELOW.match(cleaned):
        return (None, float(match.group(1)))
    if match := _ABOVE.match(cleaned):
        return (float(match.group(1)), None)
    return None


def checked_status(test: LabTest) -> Status:
    """The status to show: arithmetic where it can be done, the reader's otherwise."""
    if not test.range.strip():
        return "no_range"
    value, bounds = _number(test.value), _bounds(test.range)
    if value is None or bounds is None:
        return test.status
    low, high = bounds
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "in_range"


def recheck(analysis: LabAnalysis) -> list[dict[str, str]]:
    """Every test as it is stored: verbatim, with the checked status.

    Where the arithmetic disagrees with the reader, its own reading is kept
    beside the corrected one as `reader_status`. That disagreement is a
    reader error, and a record of how often it happens is worth having.
    """
    stored = []
    for test in analysis.tests:
        status = checked_status(test)
        row = {
            "name": test.name,
            "value": test.value,
            "unit": test.unit,
            "range": test.range,
            "status": status,
            "explanation_en": test.explanation_en,
            "explanation_hi": test.explanation_hi,
        }
        if status != test.status:
            logger.info(
                "Lab reader said %s for %r; the printed range says %s", test.status, test.name, status
            )
            row["reader_status"] = test.status
        stored.append(row)
    return stored
