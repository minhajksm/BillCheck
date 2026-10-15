"""Reading a bill and analysing it, in one call.

The reader's instructions live in `analysis_prompt.py` and the shape it returns
in `analysis.py`. It transcribes every line, normalises it, and reports what the
bill itself proves -- arithmetic that doesn't add up, a rate above a printed
MRP, a line billed twice. It never prices anything: `requires_reference_price`
is the handoff to the price lists in `references.py`, which is the only part of
this system that knows what an item costs.

Two providers, chosen by OCR_PROVIDER, the same shape as SMS delivery:

- `stub` needs no API key and returns one fixed sample analysis, so the whole
  loop runs in development and tests without a real bill leaving the machine.
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

from analysis import AnalysedLine, BillAnalysis, BillHeader, Finding, LineAttributes, Structural
from analysis_prompt import PROMPT
from db import india_today
from settings import get_settings

logger = logging.getLogger("billcheck.ocr")

# Images Claude's vision input accepts, plus PDF as a document.
SUPPORTED_IMAGES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
PDF_MEDIA = "application/pdf"


@dataclass(frozen=True)
class BillPage:
    data: bytes
    content_type: str


class OcrError(Exception):
    """The pages couldn't be read. The caller tells the user to retake them."""


class OcrProvider(Protocol):
    def read_bill(self, pages: list[BillPage]) -> BillAnalysis: ...


def _blank() -> LineAttributes:
    return LineAttributes(
        size="", gauge="", french="", volume="", strength="", pack_size="", material="", brand=""
    )


# The prototype's day 3 bill. Sample data, not a real patient or hospital.
# (section, verbatim, plain, category, quantity, unit, rate, amount, mrp)
#
# The dated lines are dated today, read from the clock rather than written in.
# A date written in would sit inside the stay the day it was typed and drift
# outside it a week later, so every test that turns on the stay check would
# start failing on a date nobody chose.
STUB_LINES = [
    (
        "Room",
        "Room rent, twin sharing",
        "Room rent, twin sharing",
        "room_and_nursing",
        1,
        "day",
        6500,
        6500,
        None,
    ),
    ("Room", "Nursing charges", "Nursing charges", "room_and_nursing", 1, "day", 2200, 2200, None),
    (
        "Doctor",
        "Consultant visit, Dr. A. Mehta",
        "Consultant visit",
        "professional_fees",
        1,
        "visit",
        2500,
        2500,
        None,
    ),
    (
        "Doctor",
        "Consultant visit, Dr. A. Mehta",
        "Consultant visit",
        "professional_fees",
        1,
        "visit",
        2500,
        2500,
        None,
    ),
    (
        "Pharmacy",
        "Inj. Meropenem 1g",
        "Meropenem injection 1g",
        "pharmacy_drug",
        6,
        "vial",
        2950,
        17700,
        1840,
    ),
    (
        "Pharmacy",
        "Inj. Pantoprazole 40mg",
        "Pantoprazole injection",
        "pharmacy_drug",
        2,
        "vial",
        60,
        120,
        None,
    ),
    (
        "Pharmacy",
        "IV fluid, Ringer lactate 500ml",
        "Ringer lactate IV fluid",
        "pharmacy_drug",
        4,
        "bottle",
        130,
        520,
        None,
    ),
    ("Lab", "CBC and CRP tests", "Blood count and CRP", "investigation", 1, "set", 1450, 1450, None),
    ("Imaging", "Chest X-ray", "Chest X-ray", "investigation", 1, "view", 950, 950, None),
    (
        "Consumables",
        "Surgical gloves",
        "Surgical gloves",
        "consumable_disposable",
        80,
        "pair",
        85,
        6800,
        None,
    ),
    (
        "Consumables",
        "Syringes and IV cannula",
        "Syringes and IV cannula",
        "consumable_disposable",
        1,
        "set",
        1250,
        1250,
        None,
    ),
]

# One finding the stub always makes, so the whole path is exercised in
# development without a key. It is a hard one the bill itself proves: the
# billed rate is above the MRP printed beside it.
STUB_FINDINGS = [
    Finding(
        finding_id="f1",
        rule="B. billed rate above printed MRP",
        severity="high",
        line_ids=["L5"],
        evidence_quoted="Inj. Meropenem 1g — rate 2,950 — MRP 1,840",
        statement=(
            "The bill charges Rs 2,950 per vial for Inj. Meropenem 1g against an MRP of "
            "Rs 1,840 printed on the same line."
        ),
        confirmation_required="The MRP printed on the pack supplied.",
    ),
    Finding(
        finding_id="f2",
        rule="C. identical item billed twice on the same date",
        severity="medium",
        line_ids=["L3", "L4"],
        evidence_quoted="Consultant visit, Dr. A. Mehta — 2,500 — twice",
        statement="Two consultant visits by the same doctor are billed for the same date.",
        confirmation_required="The case sheet showing two separate visits.",
    ),
]


# The lines the sample bill dates. Everything else carries a quantity
# instead, which is how most of a bill reads.
STUB_DATED = frozenset({"Consultant visit, Dr. A. Mehta"})


class StubOcr:
    """Development and tests: returns one fixed sample analysis, whatever is sent.

    It exists so the scan loop, the review and every screen can be exercised
    without an API key and without a real bill leaving the machine.
    """

    def read_bill(self, pages: list[BillPage]) -> BillAnalysis:
        if not pages:
            raise OcrError("No pages to read.")
        logger.warning("Stub OCR: returning the sample bill, not reading the %d page(s) sent", len(pages))

        today = india_today().strftime("%d %b")
        lines = [
            AnalysedLine(
                line_id=f"L{number}",
                page=1,
                section=section,
                description_verbatim=verbatim,
                item_name_plain=plain,
                category=category,  # type: ignore[arg-type]
                attributes=_blank(),
                quantity=float(quantity),
                unit=unit,
                rate=float(rate),
                amount=float(amount),
                date=today if verbatim in STUB_DATED else "",
                mrp_printed=None if mrp is None else float(mrp),
                confidence=0.9,
                ambiguous=False,
                ambiguity_reason="",
            )
            for number, (section, verbatim, plain, category, quantity, unit, rate, amount, mrp) in enumerate(
                STUB_LINES, start=1
            )
        ]
        total = float(sum(line.amount or 0 for line in lines))
        return BillAnalysis(
            error="",
            bill=BillHeader(
                hospital="City Care Hospital",
                bill_no="",
                bill_date="",
                admission_date="",
                discharge_date="",
                stay_days=None,
                room_category="Twin sharing",
                total=total,
                pages_processed=len(pages),
                extraction_confidence=0.9,
            ),
            lines=lines,
            findings=[finding.model_copy(deep=True) for finding in STUB_FINDINGS],
            requires_reference_price=["L10", "L11"],
            structural=Structural(
                consumable_share_pct=round(100 * 8050 / total, 1),
                unitemised_share_pct=0.0,
                unreadable_line_count=0,
            ),
            needs_human_review=False,
            review_reasons=[],
        )


def _loggable(request: dict) -> str:
    """The request as sent, with two substitutions for a terminal's sake.

    A page is tens of thousands of characters of base64, which would bury
    everything worth reading, so each one becomes its size. `output_format` is
    a class; what actually goes over the wire is its JSON schema, so that is
    what is shown -- and it is the part worth looking at when the API rejects
    a request as too complex.
    """
    import copy
    import json

    shown = {key: value for key, value in request.items() if key != "output_format"}
    shown = copy.deepcopy(shown)
    for message in shown.get("messages", []):
        for block in message.get("content", []):
            source = block.get("source", {}) if isinstance(block, dict) else {}
            if "data" in source:
                source["data"] = f"<base64, {len(source['data']):,} chars>"

    output_format = request.get("output_format")
    if output_format is not None:
        shown["output_format_schema"] = output_format.model_json_schema()

    try:
        return json.dumps(shown, indent=2, ensure_ascii=False)
    except TypeError:
        return repr(shown)


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

    def read_bill(self, pages: list[BillPage]) -> BillAnalysis:
        import anthropic

        if not pages:
            raise OcrError("No pages to read.")

        content: list[dict] = [self._block(page, index) for index, page in enumerate(pages, start=1)]
        content.append(
            {
                "type": "text",
                "text": "Analyse this hospital bill. Work the four phases and return the JSON object.",
            }
        )

        request = {
            "model": self._model,
            "max_tokens": 16000,
            "system": PROMPT,
            "output_config": {"effort": self._effort},
            "messages": [{"role": "user", "content": content}],
            "output_format": BillAnalysis,
        }

        # Logged before the call, so a request the API rejects is visible at
        # all: the response log below never runs when parse() raises.
        logger.warning("Sending to Claude:\n%s", _loggable(request))

        try:
            response = self._client.messages.parse(**request)
        except anthropic.APIError as exc:
            raise OcrError(f"Couldn't read the bill: {exc}") from exc

        # The whole response, verbatim, before anything here touches it. Logged
        # at WARNING so it shows with the API's default level, and logged
        # before the checks below so a refusal or an unparseable answer is
        # visible too rather than disappearing into an OcrError.
        #
        # It contains the transcribed bill, so this is a development tool: it
        # puts a patient's charges wherever the logs go.
        try:
            logger.warning("Claude responded:\n%s", response.model_dump_json(indent=2))
        except Exception:  # noqa: BLE001 - never let logging break a read
            logger.warning("Claude responded (unserialisable):\n%r", response)

        if response.stop_reason == "refusal":
            raise OcrError("The bill couldn't be read.")

        analysis = response.parsed_output
        if analysis is None:
            raise OcrError("The reader returned nothing that fits the schema.")
        if analysis.error:
            # PHASE 4: not a hospital bill, or too degraded to read.
            raise OcrError(analysis.error)
        if not analysis.lines:
            raise OcrError("No itemized lines were found on these pages.")

        logger.info(
            "Read %d line(s), %d finding(s)%s: %s",
            len(analysis.lines),
            len(analysis.findings),
            " [needs human review]" if analysis.needs_human_review else "",
            ", ".join(f"{f.rule}({f.severity})" for f in analysis.findings) or "none",
        )
        return analysis


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
