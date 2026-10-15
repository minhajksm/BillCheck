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

from typing import Literal

from pydantic import BaseModel, Field

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

Severity = Literal["high", "medium", "low"]


class LineAttributes(BaseModel):
    """The specification attributes PHASE 2 asks for, each as printed.

    Named fields rather than a free-form mapping: a `dict[str, str]` compiles
    to a schema that permits no keys at all, so the reader could never fill
    one in. These are the eight the prompt lists.
    """

    size: str = Field(description="As printed, e.g. '7.5'. Empty when not readable.")
    gauge: str = Field(description="As printed, e.g. '18G'. Empty when not readable.")
    french: str = Field(description="French size as printed. Empty when not readable.")
    volume: str = Field(description="As printed, e.g. '500ml'. Empty when not readable.")
    strength: str = Field(description="As printed, e.g. '40mg'. Empty when not readable.")
    pack_size: str = Field(description="As printed, e.g. '10s'. Empty when not readable.")
    material: str = Field(description="As printed. Empty when not readable.")
    brand: str = Field(description="As printed. Empty when not readable.")


class AnalysedLine(BaseModel):
    """One line of the bill, transcribed verbatim and then normalised."""

    line_id: str = Field(description="Your own id for this line, unique within the bill.")
    page: int = Field(description="1-based page the line appears on.")
    section: str = Field(description="The section heading above it, as printed. Empty if none.")
    description_verbatim: str = Field(description="Exactly as printed. Not cleaned or translated.")
    item_name_plain: str = Field(description="The same item in plain English.")
    category: Category
    attributes: LineAttributes
    quantity: float | None = Field(description="As printed. Null when the bill states none.")
    unit: str = Field(description="As printed, e.g. 'vial'. Empty when the bill states none.")
    rate: float | None = Field(description="Rate per unit as printed. Null when none is printed.")
    amount: float | None = Field(description="The line's amount. Null when it cannot be read.")
    date: str = Field(description="The line's date as printed. Empty when it carries none.")
    mrp_printed: float | None = Field(description="MRP, only where the bill prints one. Else null.")
    confidence: float = Field(description="0.0-1.0, how sure you are this line was read correctly.")
    ambiguous: bool = Field(description="True where the line cannot be resolved without asking.")
    ambiguity_reason: str = Field(description="What is ambiguous. Empty when it isn't.")


class Finding(BaseModel):
    """One thing PHASE 3 detected, with the evidence that fired it."""

    finding_id: str = Field(description="Your own id for this finding.")
    rule: str = Field(description="The check that fired, e.g. 'A. quantity x rate != amount'.")
    severity: Severity
    line_ids: list[str] = Field(description="`line_id`s this is about. Empty for a whole-bill finding.")
    evidence_quoted: str = Field(description="Quoted from the bill. Never paraphrased.")
    statement: str = Field(description="What the bill shows, in one or two sentences.")
    confirmation_required: str = Field(description="What would be needed to confirm it.")


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
    """PHASE 4, the whole object."""

    error: str = Field(
        description="Empty when the document read. Otherwise why it could not be analysed, "
        "with `lines` and `findings` empty."
    )
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
