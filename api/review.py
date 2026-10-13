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
"""

import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal

from audit import Flag
from ocr import ExtractedBill, Observation
from references import parse_bill_date

logger = logging.getLogger("billcheck.review")

# Rupees of slack before the rows and the printed total are called different.
# Bills round, and a figure read off a photograph can be a paisa out.
TOTAL_TOLERANCE = Decimal("1")

# What a confirmed observation is worth. Everything else is a question.
CHECKABLE = frozenset({"total_mismatch", "duplicate_line", "date_outside_stay"})

# Kinds the reference lists already decide. If the reader says the same thing,
# the cited flag wins and the reader's is dropped, so the family is asked once.
COVERED_BY_REFERENCES = {
    "unit_price_high": "above_mrp",
    "quantity_high": "quantity",
    "duplicate_line": "duplicate",
}


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


def _confirm_date(
    bill: ExtractedBill, positions: list[int], admitted_on: date, closed_on: date | None
) -> tuple[bool, dict[str, str]]:
    """A row dated outside the stay, where the row actually carries a date."""
    if not positions:
        return False, {}
    row = bill.rows[positions[0] - 1]
    on = parse_bill_date(row.detail)
    if on is None:
        return False, {}
    if admitted_on <= on <= (closed_on or date.max):
        return False, {}
    return True, {
        "row_date": on.isoformat(),
        "admitted_on": admitted_on.isoformat(),
        **({"closed_on": closed_on.isoformat()} if closed_on else {}),
    }


# Kinds where the whole line is what is being questioned, so the line's own
# amount is what a correction would give back. For the rest — "this looks dear",
# "this looks like a lot" — there is no defensible figure, and taking one from
# the reader's own estimate would dress a guess up as an amount.
WHOLE_LINE = frozenset(
    {
        "duplicate_line",
        "same_test_two_names",
        "non_medical_item",
        "service_charge_on_room",
        "package_overlap",
        "date_outside_stay",
    }
)


def _to_flag(
    observation: Observation,
    positions: list[int],
    level: str,
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
        level=level,  # type: ignore[arg-type]
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
        if not positions and observation.kind != "total_mismatch":
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

    return _renumber(reference_flags + flags)


def _renumber(flags: list[Flag]) -> list[Flag]:
    """Red first, then amber, each in the bill's own order, numbered from 1."""
    order = {"red": 0, "amber": 1}
    ordered = sorted(flags, key=lambda flag: (order[flag.level], flag.row_position))
    return [replace(flag) for flag in ordered]
