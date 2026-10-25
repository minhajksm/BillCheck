"""The shape the reader returns: PHASE 4 of the prompt, field for field.

Nothing is sent to constrain the answer, so this is the whole of what holds
the reader to its format -- and it has to be as forgiving as the prompt is,
or a perfectly good answer is thrown away. Two of the prompt's own
instructions decide that:

- ABSOLUTE CONSTRAINT 3 says to output null where a field is unreadable. So
  every text field here accepts null and keeps it as "", because a bill that
  prints no unit has no unit rather than an unreadable one, and nothing
  downstream should have to tell those apart.
- PHASE 1 says to transcribe verbatim. So a quantity arrives as the bill
  prints it, and a bed billed as "1 1/4" is a string, not a number. The
  numbers here are read through that: "1 1/4" is 1.25, "5,150.00" is 5150.0,
  and anything that is not a number at all is null rather than a refusal.

The two figures a discounted bill prints and a plain one does not --
`AnalysedLine.net_amount` and `BillHeader.discount` -- default to null rather
than being required. Most bills have no answer to give, and an answer that
omits the key says the same thing as one that sends null: there is no
discount. Failing a whole read over a key about a figure that is not on the
page is exactly the forgiveness this module is for.

What stays strict is `Finding.severity`, which decides whether a family is
shown a red flag or an amber question. There is no safe guess between
overstating what a bill proves and understating it, so an unrecognised
severity refuses the bill.

A line carries only what something downstream reads. The reading is paid for
by the second -- a bill's answer is thousands of output tokens and a family
waits for every one of them -- so a field written out and then discarded is
time taken from someone sitting in a hospital corridor. `rate` is the one
exception: nothing reads it, but "quantity x rate != amount" is the whole of
check A, and taking the operand out of the answer takes away the reader's own
working.
"""

import logging
import re
from fractions import Fraction
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator

logger = logging.getLogger("billcheck.analysis")


def _as_text(value: Any) -> Any:
    """Null becomes "", per ABSOLUTE CONSTRAINT 3.

    The reader is told to send null where a field is unreadable, and it does
    -- 15 of the 15 lines on one real bill had `"unit": null`. Downstream,
    "no unit printed" and "unit unreadable" are the same thing: nothing to
    show. Keeping both as "" means no caller has to check for None.
    """
    return "" if value is None else value


# "1 1/4", "1/4", "2", "5,150.00", "Rs. 450", "₹1,250.50", "12.5%".
_MIXED = re.compile(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$")
_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_STRIP = re.compile(r"[₹,\s]|(?i:rs\.?)|%")


def _as_number(value: Any) -> Any:
    """A figure as the bill prints it, read as a number where it is one.

    PHASE 1 asks for verbatim transcription, so a quantity comes back the way
    the bill writes it. A bed billed "1 1/4" is a real thing on a real bill
    and it is not a number to `float()`; it is 1.25 here. Anything that is
    not a figure at all becomes null, which is what the format uses for "the
    bill does not say" -- never a refusal, and never zero, because a quantity
    that is not stated is not a quantity of none.
    """
    if value is None or isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return None

    mixed = _MIXED.match(text)
    if mixed:
        whole, numerator, denominator = (int(part) for part in mixed.groups())
        if denominator:
            return whole + numerator / denominator
        return float(whole)

    fraction = _FRACTION.match(text)
    if fraction:
        numerator, denominator = (int(part) for part in fraction.groups())
        return float(Fraction(numerator, denominator)) if denominator else None

    try:
        return float(_STRIP.sub("", text))
    except ValueError:
        logger.warning("Reader sent %r where a figure was asked for; keeping it as null", value)
        return None


def _as_count(value: Any) -> Any:
    """A whole number, rounded from whatever arrived.

    Page and line counts arrive as "1" often enough, and a reader that
    answers 1.32 where a whole number was asked for is answering honestly.
    Neither is worth refusing a bill over.
    """
    number = _as_number(value)
    return number if number is None else round(number)


Text = Annotated[str, BeforeValidator(_as_text)]
"""A string field that takes the reader's null and keeps it as ""."""

Number = Annotated[float | None, BeforeValidator(_as_number)]
"""A figure, null where the bill does not state one."""

Count = Annotated[int | None, BeforeValidator(_as_count)]
"""A whole number, null where the bill does not state one."""

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

    line_id: Text = Field(description="Your own id for this line, unique within the bill.")
    description_verbatim: Text = Field(description="Exactly as printed. Not cleaned or translated.")
    category: Category
    quantity: Number = Field(description="As printed. Null when the bill states none.")
    unit: Text = Field(description="As printed, e.g. 'vial'. Empty when the bill states none.")
    rate: Number = Field(description="Rate per unit as printed. Null when none is printed.")
    amount: Number = Field(description="The line's gross amount. Null when it cannot be read.")
    net_amount: Number = Field(
        default=None,
        description="The line's amount after discount, where the bill prints a second money "
        "column for it. Null where the bill prints only one.",
    )
    date: Text = Field(description="The line's date as printed. Empty when it carries none.")
    mrp_printed: Number = Field(description="MRP, only where the bill prints one. Else null.")

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

    finding_id: Text = Field(description="Your own id for this finding.")
    rule: Text = Field(description="The check that fired, e.g. 'A. quantity x rate != amount'.")
    severity: Severity
    line_ids: list[str] = Field(description="`line_id`s this is about. Empty for a whole-bill finding.")
    evidence_quoted: Text = Field(description="Quoted from the bill. Never paraphrased.")
    statement: Text = Field(description="What the bill shows, in one or two sentences.")
    confirmation_required: Text = Field(description="What would be needed to confirm it.")

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
    hospital: Text = Field(description="As printed. Empty when not readable.")
    bill_no: Text = Field(description="As printed. Empty when not readable.")
    bill_date: Text = Field(description="As printed. Empty when not readable.")
    admission_date: Text = Field(description="As printed or supplied. Empty when neither.")
    discharge_date: Text = Field(description="As printed or supplied. Empty when neither.")
    room_category: Text = Field(description="As printed. Empty when not readable.")
    subtotal: Number = Field(
        default=None, description="The total printed before any discount. Null when none is printed."
    )
    discount: Number = Field(default=None, description="The discount printed on the bill. Null when none is.")
    total: Number = Field(description="The amount payable, after any discount. Null when none is printed.")
    amount_paid: Number = Field(
        default=None, description="The total paid, as the bill prints it. Null when it prints none."
    )
    balance: Number = Field(
        default=None,
        description="What the bill says is still due; 0 for a nil balance. Null when not printed.",
    )
    patient_name: Text = Field(description="As printed. Empty when not readable.")
    # The patient's own details, as printed: offered as a member's details
    # when the family files the bill. Empty where the bill prints none, and
    # never the hospital's own phone, email or address.
    patient_age: Text = Field(default="", description="As printed, e.g. '68 Yrs'. Empty when none.")
    patient_dob: Text = Field(default="", description="Date of birth as printed. Empty when none.")
    patient_phone: Text = Field(default="", description="The patient's number as printed. Empty when none.")
    patient_email: Text = Field(default="", description="The patient's email as printed. Empty when none.")
    patient_address: Text = Field(
        default="", description="The patient's address as printed. Empty when none."
    )
    ip_number: Text = Field(
        description="The IP, admission or registration number as printed. Empty when not readable."
    )
    pages_processed: Count = Field(description="How many pages you read.")
    extraction_confidence: Number = Field(description="0.0-1.0 across the whole document.")


class Structural(BaseModel):
    """PHASE 3 H: what the bill looks like as a whole."""

    consumable_share_pct: Number = Field(description="Consumables and disposables as a % of the total.")
    unitemised_share_pct: Number = Field(description="Catch-all and unitemised lines as a % of the total.")
    unreadable_line_count: Count = Field(description="Lines that could not be read.")


class Payment(BaseModel):
    """One deposit, advance or receipt the bill lists, as printed."""

    date: Text = ""
    mode: Text = ""
    amount: Number = None


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
    # What has been paid towards it. Optional like the money fields above:
    # most interim bills list none, and an answer that leaves the key out says
    # the same thing.
    payments: list[Payment] = Field(default_factory=list)
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
        # A reader that states no confidence is not a reader stating none: an
        # absent figure says nothing either way, so it does not condemn a read.
        confidence = self.bill.extraction_confidence
        if self.needs_human_review and not self.findings and confidence is not None and confidence < 0.5:
            # Read badly enough that the reader itself asked for a human, with
            # nothing to show for the read. Not a report to put in front of a
            # family as though the bill were clean.
            return "; ".join(self.review_reasons) or "The reader could not read these pages."
        return ""
