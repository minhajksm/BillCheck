"""Deciding what the reader's observations are worth.

The reader looks at the page and says what it noticed. Some of what it says can
be checked against the rows it transcribed, and some can't. This module does
that checking, and it is the whole reason model findings can be shown at all.

Three outcomes for an observation:

- **Confirmed.** The claim was checkable and the arithmetic agrees. It becomes
  a flag that says what it says.
- **Unconfirmable.** Nothing here can prove or disprove it — "this looks dear
  for a pair of gloves" rests on what the reader knows, not on the bill. It
  becomes an amber flag, which in this app means a question.
- **Dropped.** The claim was checkable and the check disagreed, or it points at
  rows that don't exist, or a reference list already covers it. Nothing is
  shown, and the disagreement is logged: that log is the eval set for how well
  the reader is doing.

Note the asymmetry. Checking can only *reject* a judgment call, never confirm
one, so no observation that rests on the reader's knowledge is ever red. Red
means we can show the family where the number came from.

One check does not wait to be proposed. A row dated outside the admission is
decidable from the rows and the case record alone, and the reader is never told
when the admission was, so `_rows_outside_stay` scans for it directly.
"""

import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal

from audit import Flag, FlagLevel
from flag_kinds import BILL_LEVEL, CHECKABLE, COVERED_BY_REFERENCES, WHOLE_LINE
from ocr import ExtractedBill, Observation
from references import parse_bill_date

logger = logging.getLogger("billcheck.review")

# Rupees of slack before the rows and the printed total are called different.
# Bills round, and a figure read off a photograph can be a paisa out.
TOTAL_TOLERANCE = Decimal("1")


def _amount(value: Decimal) -> str:
    """Money for the app to print: "11950", not "11950.0". Amounts summed from
    figures read off a photograph arrive as floats."""
    whole = value.to_integral_value()
    return str(whole if value == whole else value.normalize())


def _rows_of(observation: Observation, row_count: int) -> list[int]:
    """The rows an observation points at, dropping any that don't exist.

    A position out of range means the reader lost track of its own numbering,
    which is reason enough not to show the family anything about it.
    """
    return [position for position in observation.row_positions if 1 <= position <= row_count]


def _confirm_total(bill: ExtractedBill) -> tuple[bool, dict[str, str]]:
    """Adds the rows up. The claim stands only if they really don't match."""
    if bill.stated_total is None:
        return False, {}
    summed = sum((Decimal(str(row.amount)) for row in bill.rows), Decimal("0"))
    stated = Decimal(str(bill.stated_total))
    difference = (stated - summed).copy_abs()
    if difference <= TOTAL_TOLERANCE:
        return False, {}
    return True, {
        "stated": _amount(stated),
        "summed": _amount(summed),
        "difference": _amount(difference),
    }


def _confirm_duplicate(bill: ExtractedBill, positions: list[int]) -> tuple[bool, dict[str, str]]:
    """Two rows are a duplicate only if they really are the same row twice."""
    if len(positions) < 2:
        return False, {}
    rows = [bill.rows[position - 1] for position in positions[:2]]
    first, second = rows
    same = (
        first.name.strip().casefold() == second.name.strip().casefold()
        and (first.detail or "").strip().casefold() == (second.detail or "").strip().casefold()
        and first.amount == second.amount
    )
    if not same:
        return False, {}
    return True, {"repeated_detail": first.detail or "", "first_row_position": str(positions[0])}


def date_detail(on: date, admitted_on: date, closed_on: date | None) -> dict[str, str]:
    """What the app shows a family: the row's date, and the stay it is outside."""
    return {
        "row_date": on.isoformat(),
        "admitted_on": admitted_on.isoformat(),
        **({"closed_on": closed_on.isoformat()} if closed_on else {}),
    }


def _bill_year(bill: ExtractedBill, admitted_on: date) -> int:
    """The year to read a row's date in, where the row prints none.

    Bills routinely print "11 Oct" and leave the year off. Falling back to the
    current year would misdate every row of an older bill by years and flag the
    whole thing, so the bill's own date is preferred, then the admission's.
    """
    if bill.bill_date:
        try:
            return date.fromisoformat(bill.bill_date).year
        except ValueError:
            pass
    return admitted_on.year


def _confirm_date(
    bill: ExtractedBill, positions: list[int], admitted_on: date, closed_on: date | None
) -> tuple[bool, dict[str, str]]:
    """A row dated outside the stay, where the row actually carries a date."""
    if not positions:
        return False, {}
    row = bill.rows[positions[0] - 1]
    on = parse_bill_date(row.detail, _bill_year(bill, admitted_on))
    if on is None:
        return False, {}
    if admitted_on <= on <= (closed_on or date.max):
        return False, {}
    return True, date_detail(on, admitted_on, closed_on)


def _rows_outside_stay(
    bill: ExtractedBill, admitted_on: date, closed_on: date | None
) -> list[tuple[int, date]]:
    """Every row whose own date falls outside the stay.

    This is the one check that runs over all the rows rather than waiting for
    the reader to raise it. The reader is never told when the admission was, so
    it cannot judge this; and both dates are already in hand, so comparing them
    is not something to ask a model to do.
    """
    until = closed_on or date.max
    year = _bill_year(bill, admitted_on)
    outside = []
    for position, row in enumerate(bill.rows, start=1):
        on = parse_bill_date(row.detail, year)
        if on is not None and not admitted_on <= on <= until:
            outside.append((position, on))
    return outside


def _to_flag(
    observation: Observation,
    positions: list[int],
    level: FlagLevel,
    numbers: dict[str, str],
    bill: ExtractedBill,
) -> Flag:
    """A flag from an observation. `reference_source` is "reader", which is how
    the app knows to word it as something noticed rather than something cited."""
    billed = Decimal(str(bill.rows[positions[0] - 1].amount)) if positions else Decimal("0")

    if observation.kind in WHOLE_LINE:
        excess = billed
    elif observation.kind == "total_mismatch":
        excess = Decimal(numbers.get("difference", "0"))
    else:
        excess = Decimal("0")

    return Flag(
        kind=observation.kind,
        level=level,
        row_position=positions[0] if positions else 0,
        billed=billed,
        reference_amount=billed - excess,
        reference_source="reader",
        excess=excess,
        reference_detail={
            **observation.numbers(),
            **numbers,
            "confidence": observation.confidence,
            "rows": ",".join(str(p) for p in positions),
        },
    )


def review(
    bill: ExtractedBill,
    reference_flags: list[Flag],
    admitted_on: date,
    closed_on: date | None = None,
) -> list[Flag]:
    """Turns the reader's observations into flags, or drops them.

    `reference_flags` are what the price lists already found. Where the reader
    says the same thing about the same row, the cited flag wins.
    """
    already = {(flag.kind, flag.row_position) for flag in reference_flags}
    row_count = len(bill.rows)
    flags: list[Flag] = []

    for observation in bill.observations:
        positions = _rows_of(observation, row_count)
        if not positions and observation.kind not in BILL_LEVEL:
            logger.info("Dropped %s: points at rows that aren't there", observation.kind)
            continue

        covered = COVERED_BY_REFERENCES.get(observation.kind)
        if covered and any((covered, position) in already for position in positions):
            logger.info("Dropped %s on row %s: a reference list already says it", observation.kind, positions)
            continue

        if observation.kind in CHECKABLE:
            match observation.kind:
                case "total_mismatch":
                    held, numbers = _confirm_total(bill)
                case "duplicate_line":
                    held, numbers = _confirm_duplicate(bill, positions)
                case _:
                    held, numbers = _confirm_date(bill, positions, admitted_on, closed_on)

            if not held:
                # The reader claimed something the rows don't bear out. This is
                # the signal worth keeping: it is either a misread page or a
                # reader that over-reports, and both matter.
                logger.warning(
                    "Dropped %s on rows %s: the rows don't bear it out (%s)",
                    observation.kind,
                    positions,
                    observation.note,
                )
                continue

            # Even confirmed, these rest on figures read off a photograph, so
            # they are questions about what the page says, not verdicts.
            flags.append(_to_flag(observation, positions, "amber", numbers, bill))
            continue

        # Nothing can check this one. It stands as a question or not at all.
        if observation.confidence == "low":
            logger.info("Dropped %s: the reader wasn't sure", observation.kind)
            continue
        flags.append(_to_flag(observation, positions, "amber", {}, bill))

    # The stay check, which nobody had to propose.
    raised = {flag.row_position for flag in flags if flag.kind == "date_outside_stay"}
    for position, on in _rows_outside_stay(bill, admitted_on, closed_on):
        if position in raised:
            continue
        # Synthesised so this takes the same path as a confirmed observation:
        # one way of building a flag, one shape of reference_detail.
        checked = Observation(
            kind="date_outside_stay",
            row_positions=[position],
            confidence="high",
            note="Checked against the stay; the reader did not raise it.",
        )
        logger.info("Row %d is dated %s, outside the stay", position, on.isoformat())
        flags.append(_to_flag(checked, [position], "amber", date_detail(on, admitted_on, closed_on), bill))

    return _renumber(reference_flags + flags)


def _renumber(flags: list[Flag]) -> list[Flag]:
    """Red first, then amber, each in the bill's own order, numbered from 1."""
    order = {"red": 0, "amber": 1}
    ordered = sorted(flags, key=lambda flag: (order[flag.level], flag.row_position))
    return [replace(flag) for flag in ordered]
