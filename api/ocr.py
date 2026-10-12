"""Reading an itemized bill photo into line items.

Two providers, chosen by OCR_PROVIDER, the same shape as SMS delivery:

- `stub` needs no API key and returns one fixed sample bill. It makes the whole
  scan loop work in development and in tests without sending a photograph of
  someone's hospital stay anywhere.
- `claude` reads the real pages.

Pages are never written to disk. They arrive, are read, and are dropped, so the
only health data kept is the structured bill.
"""

import base64
import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Protocol

from pydantic import BaseModel, Field

from settings import get_settings

logger = logging.getLogger("billcheck.ocr")

# What Claude's vision input accepts. A HEIC photo has to be converted first.
SUPPORTED_MEDIA = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})

PROMPT = """You are reading a photographed hospital bill from India.

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
- Leave out totals, subtotals, taxes and balance-due lines.
"""


@dataclass(frozen=True)
class BillImage:
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


class ExtractedBill(BaseModel):
    bill_date: str | None = Field(
        default=None, description="The bill date as printed, in YYYY-MM-DD form if it can be read."
    )
    rows: list[ExtractedRow] = Field(default_factory=list)


class OcrError(Exception):
    """The pages couldn't be read. The caller tells the user to retake them."""


class OcrProvider(Protocol):
    def read_bill(self, pages: list[BillImage]) -> ExtractedBill: ...


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


class StubOcr:
    """Development and tests: returns one fixed sample bill, whatever is sent.

    It exists so the scan loop, the audit and every screen can be exercised
    without an API key and without a real bill leaving the machine.
    """

    def read_bill(self, pages: list[BillImage]) -> ExtractedBill:
        if not pages:
            raise OcrError("No pages to read.")
        logger.warning("Stub OCR: returning the sample bill, not reading the %d page(s) sent", len(pages))
        return ExtractedBill(
            bill_date=None,
            rows=[
                ExtractedRow(name=name, detail=detail, quantity=quantity, amount=float(amount))
                for name, detail, quantity, amount in STUB_ROWS
            ],
        )


class ClaudeOcr:
    """Reads the pages with Claude's vision input.

    Structured outputs, not tool use: forced tool choice is rejected on current
    models, and a schema is what we want anyway.
    """

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def read_bill(self, pages: list[BillImage]) -> ExtractedBill:
        import anthropic

        if not pages:
            raise OcrError("No pages to read.")

        content: list[dict] = []
        for index, page in enumerate(pages, start=1):
            if page.content_type not in SUPPORTED_MEDIA:
                raise OcrError(f"Page {index} is a {page.content_type}, which can't be read.")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": page.content_type,
                        "data": base64.standard_b64encode(page.data).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": "Transcribe every itemized row on these pages."})

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=PROMPT,
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
            return ClaudeOcr(api_key=settings.anthropic_api_key, model=settings.ocr_model)
