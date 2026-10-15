"""Turning the reader's findings into flags a family can be shown.

The reader no longer proposes a kind from a fixed list and leaves us to
re-check it. It states what the bill proves, quotes the evidence, and says what
would be needed to confirm it -- so this module's job is smaller than it was:
order the findings, attach each to the line it is about, and carry its words
through.

Two things it still does itself. It does not price anything:
`requires_reference_price` names the lines whose rate the bill alone cannot
settle, `audit.py` answers those from the published lists, and a cited flag
always outranks a finding about the same line. And it runs the stay check,
because the reader is never told when the admission was: both dates are
already in hand here, so comparing them is not something to ask a model to do.
"""

import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal

from analysis import BillAnalysis, Finding
from audit import Flag, FlagLevel
from references import parse_bill_date

logger = logging.getLogger("billcheck.review")

# A finding the bill itself proves is as hard as a price-list flag; the prompt
# reserves "high" for exactly that. Everything else is a question.
_LEVEL: dict[str, FlagLevel] = {"high": "red", "medium": "amber", "low": "amber"}

# Red before amber, then in the bill's own order.
_ORDER = {"red": 0, "amber": 1}

STAY_KIND = "date_outside_stay"


def date_detail(on: date, admitted_on: date, closed_on: date | None) -> dict[str, str]:
    """What the app shows a family: the row's date, and the stay it is outside."""
    return {
        "row_date": on.isoformat(),
        "admitted_on": admitted_on.isoformat(),
        **({"closed_on": closed_on.isoformat()} if closed_on else {}),
    }


def _bill_year(analysis: BillAnalysis, admitted_on: date) -> int:
    """The year to read a line's date in, where the line prints none.

    Bills routinely print "11 Oct" and leave the year off. Falling back to the
    current year would misdate every line of an older bill by years and flag
    the whole thing, so the bill's own date is preferred, then the admission's.
    """
    for printed in (analysis.bill.bill_date, analysis.bill.admission_date):
        # Printed as the bill prints it, per PHASE 1, so read it the same way
        # a line's own date is read rather than assuming one format.
        on = parse_bill_date(printed, admitted_on.year)
        if on is not None:
            return on.year
    return admitted_on.year


def _outside_stay(
    analysis: BillAnalysis, admitted_on: date, closed_on: date | None
) -> list[tuple[int, date]]:
    """Every line whose own date falls outside the stay, by 1-based position.

    The one check that runs over all the lines rather than waiting for the
    reader to raise it. The reader is given the bill and nothing else, so it
    cannot know when this admission was.
    """
    until = closed_on or date.max
    year = _bill_year(analysis, admitted_on)
    outside = []
    for position, line in enumerate(analysis.lines, start=1):
        on = parse_bill_date(line.date, year)
        if on is not None and not admitted_on <= on <= until:
            outside.append((position, on))
    return outside


def _positions(analysis: BillAnalysis, finding: Finding) -> list[int]:
    """The 1-based positions of the lines a finding names, in bill order."""
    by_id = {line.line_id: position for position, line in enumerate(analysis.lines, start=1)}
    return [by_id[line_id] for line_id in finding.line_ids if line_id in by_id]


def _billed(analysis: BillAnalysis, positions: list[int]) -> Decimal:
    line = analysis.lines[positions[0] - 1] if positions else None
    return Decimal(str(line.amount)) if line and line.amount is not None else Decimal("0")


def _to_flag(analysis: BillAnalysis, finding: Finding, positions: list[int]) -> Flag:
    """A flag carrying the reader's own words.

    `statement` goes in as `why_en` because that is the field the app shows in
    place of its own wording. The rest -- the rule, the quoted evidence, what
    would confirm it -- rides along for the report and for anyone reading the
    database later.
    """
    billed = _billed(analysis, positions)
    return Flag(
        kind="analysis_finding",
        level=_LEVEL.get(finding.severity, "amber"),
        row_position=positions[0] if positions else 0,
        billed=billed,
        # The prompt forbids pricing, so a finding never asserts an amount back.
        # Where money is recoverable it is the price lists that say so.
        reference_amount=billed,
        reference_source="reader",
        excess=Decimal("0"),
        reference_detail={
            "rule": finding.rule,
            "severity": finding.severity,
            "evidence": finding.evidence_quoted,
            "confirm": finding.confirmation_required,
            "lines": ",".join(finding.line_ids),
            "why_en": finding.statement,
        },
    )


def _stay_flag(analysis: BillAnalysis, position: int, detail: dict[str, str]) -> Flag:
    """A line dated outside the stay. Correcting it takes the whole line off."""
    billed = _billed(analysis, [position])
    return Flag(
        kind=STAY_KIND,
        level="amber",
        row_position=position,
        billed=billed,
        reference_amount=Decimal("0"),
        reference_source="reader",
        excess=billed,
        reference_detail={**detail, "confidence": "high", "rows": str(position)},
    )


def flags_from_findings(
    analysis: BillAnalysis,
    reference_flags: list[Flag],
    admitted_on: date | None = None,
    closed_on: date | None = None,
    *,
    keep_all: bool = True,
) -> list[Flag]:
    """Every finding as a flag, with the stay check and the price-list flags.

    `keep_all` off drops the findings the reader itself called low severity.
    On -- the default, and what REVIEW_KEEP_ALL sets -- nothing is dropped, so
    what a bill produces can be read in full.

    `admitted_on` left out turns the stay check off, which is for reading a
    bill on its own, with no case behind it. Every bill a family uploads has
    one.
    """
    flags: list[Flag] = []
    for finding in analysis.findings:
        if not keep_all and finding.severity == "low":
            logger.warning("Dropped %s: low severity (%s)", finding.rule, finding.statement)
            continue
        positions = _positions(analysis, finding)
        if finding.line_ids and not positions:
            # Named lines that aren't in the transcription: the reader lost its
            # own numbering, and there is no line for the flag to hang on.
            logger.warning("Dropped %s: names lines %s that aren't there", finding.rule, finding.line_ids)
            continue
        flags.append(_to_flag(analysis, finding, positions))

    if admitted_on is not None:
        for position, on in _outside_stay(analysis, admitted_on, closed_on):
            logger.info("Line %d is dated %s, outside the stay", position, on.isoformat())
            flags.append(_stay_flag(analysis, position, date_detail(on, admitted_on, closed_on)))

    if analysis.needs_human_review:
        logger.warning(
            "Reader asked for human review: %s", "; ".join(analysis.review_reasons) or "no reason given"
        )

    return _renumber(reference_flags + flags)


def _renumber(flags: list[Flag]) -> list[Flag]:
    """Red first, then amber, each in the bill's own order, numbered from 1."""
    ordered = sorted(flags, key=lambda flag: (_ORDER[flag.level], flag.row_position))
    return [replace(flag) for flag in ordered]
