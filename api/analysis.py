"""The shape the reader returns, matching PHASE 4 of the prompt.

One deviation, forced by structured outputs: the prompt's two shapes -- the
analysis, or `{"error": ..., "needs_human_review": true}` -- are one object
here with an `error` field, empty when the document read. A schema can't be
"either of these two things" without a union that costs more than it buys, and
an error response is simply this object with `error` set and nothing in
`lines`.

Every field is required. An optional field on a list element compiles to a
grammar that must accept any subset of the fields in any order, and the API
rejects the request outright once that grows too large -- which is exactly
what happened to the schema this replaces. So "not applicable" is an empty
string, and null is kept only where it means something a blank cannot: a
quantity that is not stated is not a quantity of zero.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("billcheck.analysis")

Category = Literal[
    "room_and_nursing",
    "professional_fees",
    "procedure_or_ot",
    "investigation",
    "pharmacy_drug",
    "consumable_disposable",
    "implant_device",
    "equipment_charge",
    "non_medical",
    "unclassified",
]

# PHASE 2's categories in the order a bill is read, not the order the prompt
# lists them: where the money usually goes first, and the catch-all last. The
# report groups by this, so it is what a family sees.
CATEGORY_ORDER: tuple[Category, ...] = (
    "room_and_nursing",
    "professional_fees",
    "procedure_or_ot",
    "investigation",
    "pharmacy_drug",
    "consumable_disposable",
    "implant_device",
    "equipment_charge",
    "non_medical",
    "unclassified",
)

Severity = Literal["high", "medium", "low"]


class AnalysedLine(BaseModel):
    """One line of the bill, transcribed verbatim and then normalised."""

    line_id: str = Field(description="Your own id for this line, unique within the bill.")
    page: int = Field(description="1-based page the line appears on.")
    section: str = Field(description="The section heading above it, as printed. Empty if none.")
    description_verbatim: str = Field(description="Exactly as printed. Not cleaned or translated.")
    item_name_plain: str = Field(description="The same item in plain English.")
    category: Category
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "PHASE 2's specification attributes, whichever the bill prints: size, gauge, "
            "French, volume, strength, pack size, material, brand. Open rather than a fixed "
            "set of keys, because a bill prints what it prints."
        ),
    )
    quantity: float | None = Field(description="As printed. Null when the bill states none.")
    unit: str = Field(description="As printed, e.g. 'vial'. Empty when the bill states none.")
    rate: float | None = Field(description="Rate per unit as printed. Null when none is printed.")
    amount: float | None = Field(description="The line's amount. Null when it cannot be read.")
    date: str = Field(description="The line's date as printed. Empty when it carries none.")
    mrp_printed: float | None = Field(description="MRP, only where the bill prints one. Else null.")
    confidence: float = Field(description="0.0-1.0, how sure you are this line was read correctly.")
    ambiguous: bool = Field(description="True where the line cannot be resolved without asking.")
    ambiguity_reason: str = Field(description="What is ambiguous. Empty when it isn't.")

    @field_validator("category", mode="before")
    @classmethod
    def _known_category(cls, value: Any) -> Any:
        """A category we don't recognise becomes the catch-all, not a refusal.

        Nothing is enforcing the shape any more, so the reader can write
        "Pharmacy" where PHASE 2 asked for "pharmacy_drug". The only thing
        this field decides is which heading a line sits under in the report,
        and the wrong heading on one line is a far smaller harm than throwing
        away a bill a family can otherwise read. Compare `Finding.severity`,
        where the cost of guessing is a verdict.
        """
        if not isinstance(value, str):
            return value
        tidied = value.strip().lower().replace(" ", "_").replace("-", "_")
        if tidied in CATEGORY_ORDER:
            return tidied
        logger.warning("Reader sent category %r, filing the line as unclassified", value)
        return "unclassified"


class Finding(BaseModel):
    """One thing PHASE 3 detected, with the evidence that fired it."""

    finding_id: str = Field(description="Your own id for this finding.")
    rule: str = Field(description="The check that fired, e.g. 'A. quantity x rate != amount'.")
    severity: Severity
    line_ids: list[str] = Field(description="`line_id`s this is about. Empty for a whole-bill finding.")
    evidence_quoted: str = Field(description="Quoted from the bill. Never paraphrased.")
    statement: str = Field(description="What the bill shows, in one or two sentences.")
    confirmation_required: str = Field(description="What would be needed to confirm it.")

    @field_validator("severity", mode="before")
    @classmethod
    def _known_severity(cls, value: Any) -> Any:
        """Case and spacing are forgiven. An unrecognised severity is not.

        This is the field that decides whether a family is shown a red flag
        or an amber question, so there is no safe guess: reading "serious" as
        amber understates what the bill proves, and as red overstates it.
        A bill whose severities can't be read is refused instead, and the
        family is asked to retake it.
        """
        return value.strip().lower() if isinstance(value, str) else value


class BillHeader(BaseModel):
    hospital: str = Field(description="As printed. Empty when not readable.")
    bill_no: str = Field(description="As printed. Empty when not readable.")
    bill_date: str = Field(description="As printed, YYYY-MM-DD where it can be read. Else empty.")
    admission_date: str = Field(description="YYYY-MM-DD where readable or supplied. Else empty.")
    discharge_date: str = Field(description="YYYY-MM-DD where readable or supplied. Else empty.")
    stay_days: int | None = Field(description="Days of stay. Null when the dates don't give it.")
    room_category: str = Field(description="As printed. Empty when not readable.")
    total: float | None = Field(description="The grand total printed. Null when none is printed.")
    pages_processed: int = Field(description="How many pages you read.")
    extraction_confidence: float = Field(description="0.0-1.0 across the whole document.")


class Structural(BaseModel):
    """PHASE 3 H: what the bill looks like as a whole."""

    consumable_share_pct: float = Field(description="Consumables and disposables as a % of the total.")
    unitemised_share_pct: float = Field(description="Catch-all and unitemised lines as a % of the total.")
    unreadable_line_count: int = Field(description="Lines that could not be read.")


class BillAnalysis(BaseModel):
    """PHASE 4, the whole object, field for field.

    Nothing is added to the prompt's shape and nothing is left out, so the
    JSON the reader is asked for and the JSON this parses are the same
    document. Fields the pipeline never reads are still here, because the
    prompt asks the reader to produce them and the four phases are the
    method -- PHASE 3 H's percentages are arrived at by classifying every
    line, not by being asked for a percentage.
    """

    bill: BillHeader
    lines: list[AnalysedLine]
    findings: list[Finding]
    requires_reference_price: list[str] = Field(
        description="`line_id` of every consumable, disposable and device line whose rate cannot "
        "be assessed from the bill alone. Never price them."
    )
    structural: Structural
    needs_human_review: bool
    review_reasons: list[str]

    def line(self, line_id: str) -> AnalysedLine | None:
        return next((line for line in self.lines if line.line_id == line_id), None)

    def unreadable(self) -> str:
        """Why this bill can't be shown to a family, or "" when it can.

        PHASE 4's own last instruction: a document that isn't a hospital bill,
        or is too degraded, comes back asking for human review. There is no
        `error` field to read -- the format has none -- so this is the same
        judgement made from the fields the format does have.
        """
        if not self.lines:
            reasons = "; ".join(self.review_reasons)
            return f"No itemized lines were found on these pages. {reasons}".strip()
        if self.needs_human_review and not self.findings and self.bill.extraction_confidence < 0.5:
            # Read badly enough that the reader itself asked for a human, with
            # nothing to show for the read. Not a report to put in front of a
            # family as though the bill were clean.
            return "; ".join(self.review_reasons) or "The reader could not read these pages."
        return ""
