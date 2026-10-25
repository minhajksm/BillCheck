"""Re-checking stored bills when the admission dates change.

A case's dates are typed by hand at the counter, so they get corrected later:
the wrong month, a discharge a day out. What was derived from them is already
on disk by then: the `date_outside_stay` flags `review.py` raised when the
bill was read.

Leaving those alone would put the review design the wrong way round. The whole
point of re-checking the reader's claims is that a family is never shown a
question the rows don't bear out; a corrected admission date that leaves the
old flags on screen is the same false flag arriving by a different route.

One rule holds the line on history: a flag the family has already settled is
never removed. If the hospital corrected a charge, that happened, and the
amount recovered stays recovered whatever the dates say afterwards.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from references import parse_bill_date
from review import date_detail
from tables import Bill, Case, Flag, LineItem

logger = logging.getLogger("faircare.stay")

KIND = "date_outside_stay"

# Red before amber, then in the bill's own order: the same order `review.py`
# numbers flags in, so a re-checked bill reads like a freshly read one.
_LEVEL_ORDER = {"red": 0, "amber": 1}


def _outside(items: list[LineItem], year: int, admitted_on: date, closed_on: date | None) -> dict[int, date]:
    """Rows whose own date falls outside the stay, by position."""
    until = closed_on or date.max
    found = {}
    for item in items:
        on = parse_bill_date(item.detail, year)
        if on is not None and not admitted_on <= on <= until:
            found[item.position] = on
    return found


def recheck_stay(db: Session, case: Case) -> int:
    """Re-run the stay check over every bill in `case`. Returns flags changed.

    The caller has already changed the case's dates; this brings what was
    stored into line with them. It does not re-read any page: the rows were
    transcribed once and the dates on them haven't moved.
    """
    bills = db.scalars(
        select(Bill)
        .where(Bill.case_id == case.id)
        .options(selectinload(Bill.line_items), selectinload(Bill.flags))
    ).all()

    # No admission date, no stay for a row to fall outside of.
    admitted_on = case.admitted_on
    changed = 0
    for bill in bills:
        items = sorted(bill.line_items, key=lambda i: i.position)
        by_position = {item.position: item for item in items}
        outside = (
            {} if admitted_on is None else _outside(items, bill.bill_date.year, admitted_on, case.closed_on)
        )
        # A flag's `position` is its place in the report, not the row it is
        # about: that is `line_item_id`, which is what to match on here.
        existing = {
            next((i.position for i in items if i.id == flag.line_item_id), -1): flag
            for flag in bill.flags
            if flag.kind == KIND
        }

        for position, flag in existing.items():
            if position in outside:
                continue
            if flag.status != "open":
                # Already asked and answered. What happened, happened.
                logger.info("Kept a settled %s on bill %s row %d", KIND, bill.id, position)
                continue
            db.delete(flag)
            bill.flags.remove(flag)
            changed += 1

        # Flags raised while an admission date was assumed have just come off
        # above. With none there is nothing to raise in their place.
        if admitted_on is None:
            continue

        for position, on in outside.items():
            if position in existing:
                continue
            item = by_position.get(position)
            if item is None:
                continue
            bill.flags.append(
                Flag(
                    bill_id=bill.id,
                    line_item_id=item.id,
                    position=position,
                    kind=KIND,
                    level="amber",
                    billed=item.amount,
                    reference_amount=0,
                    reference_source="reader",
                    reference_detail={
                        **date_detail(on, admitted_on, case.closed_on),
                        "confidence": "high",
                        "rows": str(position),
                        "line_numbers": str(position),
                    },
                    excess=item.amount,
                )
            )
            changed += 1

        _renumber(bill)

    if changed:
        logger.info("Stay change on case %s: %d date flag(s) added or dropped", case.id, changed)
    return changed


def _renumber(bill: Bill) -> None:
    """Flags are shown in stored order, so it has to stay contiguous: dropping
    one from the middle would otherwise leave a gap in the report."""
    ordered = sorted(bill.flags, key=lambda flag: (_LEVEL_ORDER.get(flag.level, 1), flag.position))
    for number, flag in enumerate(ordered, start=1):
        flag.position = number
