"""Reading a bill, and noticing what looks wrong on it.

One call does both. The reader is already looking at the page, so asking it to
also say "these two rows are identical" costs a sentence, not a request.

What comes back is in two parts:

- `rows`: the bill transcribed, which everything downstream works from.
- `observations`: what the reader noticed. These are *claims*, not flags.
  `review.py` re-checks every claim it can against the rows, and only a claim
  that survives that check is shown as settled; the rest stay questions.

Observations carry a kind and numbers, never a sentence. Every word a family
reads has to exist in all three languages, so the copy is written in the app
and nothing user-facing is generated here.

Two providers, chosen by OCR_PROVIDER, the same shape as SMS delivery:

- `stub` needs no API key and returns one fixed sample bill, so the whole loop
  runs in development and tests without a real bill leaving the machine.
- `claude` reads the real pages.

Pages are never written to disk. They arrive, are read, and are dropped, so the
only health data kept is the structured bill.
"""

import base64
import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from settings import get_settings

logger = logging.getLogger("billcheck.ocr")

# Images Claude's vision input accepts, plus PDF as a document.
SUPPORTED_IMAGES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
PDF_MEDIA = "application/pdf"

# What the reader is allowed to report. Anything it notices that isn't one of
# these goes unreported rather than inventing a flag the app can't word.
ObservationKind = Literal[
    # --- Contradictions on the page itself ----------------------------------
    # These need nothing but the bill, read carefully. A clerk with a
    # calculator finds them, which is why review.py can re-check several.
    "total_mismatch",  # the rows don't add up to the printed total
    "duplicate_line",  # the same charge twice at the same moment
    "equipment_hours_exceed_stay",  # "ventilator 120 hrs" on a 3-day stay
    "date_outside_stay",  # a visit dated after discharge
    "implant_without_identity",  # an implant with no brand, batch or maker
    "rounded_amounts",  # every line landing on a suspiciously round figure
    "advance_not_deducted",  # a deposit shown on the bill but not taken off
    # --- What an experienced eye notices ------------------------------------
    # No second document, but knowledge in the reader's head: roughly what
    # things cost, what a ward uses in a day, what a package covers. Nothing
    # can confirm these, so they only ever stand as questions.
    "unit_price_high",  # a consumable or drug well above the usual price
    "branded_drug_margin",  # a brand billed where the molecule is cheap
    "capped_item_above_ceiling",  # a stent, knee or scheduled drug over its cap
    "non_medical_item",  # a carry bag, an attendant's meals
    "package_overlap",  # billed beside a package that should include it
    "nursing_billed_with_room",  # nursing in the room rate and as a line
    "service_charge_on_room",  # a service charge on top of room rent
    "quantity_high",  # 80 glove pairs in one ward day
    "visits_in_one_day",  # more consultant visits than a day plausibly holds
    "same_test_two_names",  # "CBC" and "Complete Blood Count"
    "same_drug_twice_sources",  # the same drug from pharmacy and from the ward
    "room_rate_vs_ward",  # a general ward billed at a private-room rate
    "icu_rate_on_ward_day",  # an ICU rate on a day spent in the ward
    "tax_on_exempt_item",  # GST against a category that shouldn't carry it
]

PROMPT = """You are reading an itemized hospital bill from India for a family
who will ask the billing desk about anything that looks wrong. They are not
clinicians and they are standing at a counter.

## First, transcribe

Transcribe the itemized rows exactly as printed. Do not infer, correct, convert
or price anything: a wrong transcription becomes a wrong accusation against a
hospital, which is worse than a missing row.

- `name` is the charge as written, e.g. "Inj. Meropenem 1g".
- `detail` is the quantity or date column as written, e.g. "6 vials" or
  "11 Oct, 10:30 am". Leave it null when the bill has no such column.
- `quantity` is the number of units only when the bill states one. Never guess
  it from the name, and leave it null for a date.
- `amount` is the row's rupee amount, digits only.
- Keep the printed order, and include every row, including repeated ones: a
  charge entered twice must appear twice.
- Leave out totals, subtotals, taxes and balance-due lines from `rows`. Put the
  printed grand total in `stated_total` instead.

## Then, say what you noticed

For each thing worth asking about, add an observation. `row_positions` are
1-based positions in the `rows` you just returned.

Report only these kinds.

### Contradictions on the page

These need nothing but the bill in front of you. Add the column, compare two
fields, look for an entry that should be there and isn't.

- `total_mismatch`: the rows you transcribed don't add up to the printed total.
- `duplicate_line`: the same charge appears twice for the same moment.
- `equipment_hours_exceed_stay`: billed hours for a machine exceed the stay,
  e.g. "Ventilator, 120 hrs" on a three-day admission.
- `date_outside_stay`: a row is dated before admission or after discharge.
- `implant_without_identity`: an implant or device billed with no brand, batch
  or manufacturer where the bill records those for other items.
- `rounded_amounts`: the amounts are implausibly round across the bill, as if
  each line were rounded up rather than priced.
- `advance_not_deducted`: the bill itself shows a deposit or advance paid, and
  the amount due does not take it off.

### What an experienced eye notices

No second document, but these rest on what you know: roughly what things cost
in India, what a ward uses in a day, what a package normally covers. You cannot
prove any of them from the page, so they are questions, and a wrong one costs a
family more than a missed one.

- `unit_price_high`: a consumable or drug priced well above what it usually
  costs, including a drug that looks above its MRP.
- `branded_drug_margin`: a brand billed at a large margin where you recognise
  the molecule and know the generic costs far less.
- `capped_item_above_ceiling`: a stent, knee implant or scheduled drug billed
  above the government ceiling you know applies to it.
- `non_medical_item`: an item that isn't treatment, e.g. a carry bag or an
  attendant's meals.
- `package_overlap`: something billed separately that a package named on this
  bill would normally already cover — OT charges, PPE, consumables beside a
  stent package.
- `nursing_billed_with_room`: nursing billed as its own line where the room
  rate normally includes it.
- `service_charge_on_room`: a service or administration charge on top of room
  rent.
- `quantity_high`: far more of something than a stay like this uses, e.g. 80
  pairs of gloves for one ward day.
- `visits_in_one_day`: more consultant visits on one date than a day plausibly
  holds.
- `same_test_two_names`: one test billed twice under different names, e.g.
  "CBC" and "Complete Blood Count".
- `same_drug_twice_sources`: the same drug billed once from the pharmacy and
  again as a ward charge for the same date.
- `room_rate_vs_ward`: the room rate doesn't match the ward the bill names,
  e.g. a general ward at a private-room rate.
- `icu_rate_on_ward_day`: an ICU rate charged for a date the bill shows the
  patient in a ward.
- `tax_on_exempt_item`: tax charged against a line whose category does not
  normally carry it.

Rules that matter more than finding things:

- Report what the bill shows, not what you assume. If you are unsure, use a
  lower `confidence` or leave it out. A charge that was correct, questioned at
  a counter, costs a family more than a charge you missed.
- Fill in only the figures that apply, as strings of digits: for a price,
  `unit_price` and the `expected` you would have guessed; for a quantity or a
  count of hours or visits, `quantity` and the `usual` you would expect; for a
  total or an advance, `stated` and `summed`. Leave the rest null.
- Most kinds name the rows they are about. `rounded_amounts` and
  `advance_not_deducted` are about the bill as a whole, so they may leave
  `row_positions` empty, as `total_mismatch` does.
- One finding per thing. If a package covers three lines billed separately,
  that is one `package_overlap` naming three rows, not three observations.
- `note` is your reasoning in one line, for our logs. It is never shown to
  anyone, so write it for an engineer, not for the family.
- Never write an accusation, in any field. These are questions.
"""


@dataclass(frozen=True)
class BillPage:
    data: bytes
    content_type: str


class ExtractedRow(BaseModel):
    """One row as printed on the bill."""

    name: str = Field(description="The charge exactly as written on the bill.")
    detail: str | None = Field(
        default=None, description='The quantity or date column as written, e.g. "6 vials".'
    )
    quantity: float | None = Field(
        default=None, description="Units, only where the bill states a count. Null for a date."
    )
    amount: float = Field(description="The row's amount in rupees.")


class Observation(BaseModel):
    """Something the reader noticed. A claim to check, not a flag.

    The figures are separate fields rather than a free-form mapping: a
    `dict[str, str]` becomes a schema that allows no keys at all, so under
    structured outputs the reader could never fill one in.
    """

    kind: ObservationKind
    row_positions: list[int] = Field(
        default_factory=list, description="1-based positions in `rows` this is about."
    )
    unit_price: str | None = Field(
        default=None, description="For a price: what one unit was billed at, digits only."
    )
    expected: str | None = Field(
        default=None, description="For a price: what you would have expected one unit to cost."
    )
    quantity: str | None = Field(default=None, description="For a quantity: how many were billed.")
    usual: str | None = Field(
        default=None, description="For a quantity: how many a stay like this usually uses."
    )
    stated: str | None = Field(default=None, description="For a total: the total printed on the bill.")
    summed: str | None = Field(default=None, description="For a total: what the rows add up to.")
    confidence: Literal["high", "medium", "low"] = "medium"
    note: str = Field(default="", description="One line of reasoning, for our logs only.")

    def numbers(self) -> dict[str, str]:
        """The figures that were given, for the app to put in its copy."""
        given = {
            "unit_price": self.unit_price,
            "expected": self.expected,
            "quantity": self.quantity,
            "usual": self.usual,
            "stated": self.stated,
            "summed": self.summed,
        }
        return {key: value for key, value in given.items() if value}


class ExtractedBill(BaseModel):
    bill_date: str | None = Field(
        default=None, description="The bill date as printed, in YYYY-MM-DD form if it can be read."
    )
    stated_total: float | None = Field(
        default=None, description="The grand total printed on the bill, if there is one."
    )
    rows: list[ExtractedRow] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)


class OcrError(Exception):
    """The pages couldn't be read. The caller tells the user to retake them."""


class OcrProvider(Protocol):
    def read_bill(self, pages: list[BillPage]) -> ExtractedBill: ...


# The prototype's day 3 bill. Sample data, not a real patient or hospital.
STUB_ROWS = [
    ("Room rent, twin sharing", "1 day", None, 6500),
    ("Nursing charges", "1 day", None, 2200),
    ("Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", None, 2500),
    ("Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", None, 2500),
    ("Inj. Meropenem 1g", "6 vials", 6, 17700),
    ("Inj. Pantoprazole 40mg", "2 vials", 2, 120),
    ("IV fluid, Ringer lactate 500ml", "4 bottles", 4, 520),
    ("CBC and CRP tests", "1 set", 1, 1450),
    ("Chest X-ray", "1 view", 1, 950),
    ("Surgical gloves", "80 pairs", 80, 6800),
    ("Syringes and IV cannula", "1 set", 1, 1250),
]

# One observation the stub always makes, so the review path has something to
# exercise in development without a key.
#
# It is deliberately a judgment of degree about a line the price lists don't
# cover: it shows the honest shape of a reader flag — a question, with the
# reader's own expectation shown as an expectation, and no rupee figure claimed
# behind it.
STUB_OBSERVATIONS = [
    Observation(
        kind="unit_price_high",
        row_positions=[1],
        unit_price="6500",
        expected="4000",
        confidence="medium",
        note="Stub observation: fixed, not read off the page.",
    )
]


class StubOcr:
    """Development and tests: returns one fixed sample bill, whatever is sent.

    It exists so the scan loop, the review and every screen can be exercised
    without an API key and without a real bill leaving the machine.
    """

    def read_bill(self, pages: list[BillPage]) -> ExtractedBill:
        if not pages:
            raise OcrError("No pages to read.")
        logger.warning("Stub OCR: returning the sample bill, not reading the %d page(s) sent", len(pages))
        rows = [
            ExtractedRow(name=name, detail=detail, quantity=quantity, amount=float(amount))
            for name, detail, quantity, amount in STUB_ROWS
        ]
        return ExtractedBill(
            bill_date=None,
            stated_total=float(sum(row.amount for row in rows)),
            rows=rows,
            observations=[obs.model_copy(deep=True) for obs in STUB_OBSERVATIONS],
        )


class ClaudeOcr:
    """Reads the pages with Claude and reports what it noticed.

    Structured outputs, not tool use: forced tool choice is rejected on current
    models, and a schema is what we want anyway.
    """

    def __init__(self, api_key: str, model: str, effort: str = "medium") -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._effort = effort

    @staticmethod
    def _block(page: BillPage, index: int) -> dict:
        encoded = base64.standard_b64encode(page.data).decode("ascii")
        if page.content_type == PDF_MEDIA:
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": PDF_MEDIA, "data": encoded},
            }
        if page.content_type in SUPPORTED_IMAGES:
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": page.content_type, "data": encoded},
            }
        raise OcrError(f"Page {index} is a {page.content_type}, which can't be read.")

    def read_bill(self, pages: list[BillPage]) -> ExtractedBill:
        import anthropic

        if not pages:
            raise OcrError("No pages to read.")

        content: list[dict] = [self._block(page, index) for index, page in enumerate(pages, start=1)]
        content.append(
            {
                "type": "text",
                "text": "Transcribe every itemized row on these pages, then say what you noticed.",
            }
        )

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=PROMPT,
                output_config={"effort": self._effort},
                messages=[{"role": "user", "content": content}],
                output_format=ExtractedBill,
            )
        except anthropic.APIError as exc:
            raise OcrError(f"Couldn't read the bill: {exc}") from exc

        if response.stop_reason == "refusal":
            raise OcrError("The bill couldn't be read.")

        bill = response.parsed_output
        if bill is None or not bill.rows:
            raise OcrError("No itemized rows were found on these pages.")

        logger.info(
            "Read %d row(s), %d observation(s): %s",
            len(bill.rows),
            len(bill.observations),
            ", ".join(f"{obs.kind}({obs.confidence})" for obs in bill.observations) or "none",
        )
        return bill


def to_decimal(value: float | None) -> Decimal | None:
    """Money and counts arrive as JSON numbers; everything downstream is exact."""
    return None if value is None else Decimal(str(value))


@lru_cache
def get_ocr_provider() -> OcrProvider:
    """FastAPI dependency. One provider per process."""
    settings = get_settings()
    match settings.ocr_provider:
        case "stub":
            return StubOcr()
        case "claude":
            return ClaudeOcr(
                api_key=settings.anthropic_api_key,
                model=settings.ocr_model,
                effort=settings.ocr_effort,
            )
