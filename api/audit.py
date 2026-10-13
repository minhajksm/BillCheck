"""Checks an itemized bill and raises flags.

Three checks, in the order a family would notice them:

1. **Above MRP** — a medicine billed above the price printed on its pack, or
   above its NPPA ceiling price where one applies. Red: selling above the
   printed MRP isn't allowed under India's Legal Metrology rules.
2. **Duplicate** — the same charge entered twice for the same date and time.
   Red, though it is usually a data-entry mistake rather than a second visit.
   Identical lines with no date or time are left alone: two doses look alike.
3. **Unusual quantity** — far more of something than a ward stay usually uses.
   Amber only. There may be a real reason, such as a procedure or isolation
   care, so this is a question and never a verdict.

A flag carries facts, never sentences: what was billed, what it was checked
against, and the difference. The app turns those into copy in the family's own
language, which is why nothing here is user-facing English.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from references import PACKED_UNITS, ReferenceData, is_timed, normalize, parse_count, parse_quantity

FlagKind = Literal["above_mrp", "duplicate", "quantity"]
FlagLevel = Literal["red", "amber"]

PAISE = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _count(value: Decimal) -> str:
    """A count for the app to print: "80", not "80.0". Bills count whole
    things, and a quantity read off a photo arrives as a float."""
    whole = value.to_integral_value()
    return str(whole if value == whole else value.normalize())


@dataclass(frozen=True)
class BillRow:
    """One line of the bill as it was read off the page."""

    position: int
    name: str
    detail: str | None = None
    quantity: Decimal | None = None
    amount: Decimal = Decimal("0")

    def count(self) -> Decimal | None:
        """How many units this line covers, from the quantity column if the
        bill had one, otherwise from the quantity as printed."""
        return self.quantity if self.quantity is not None else parse_quantity(self.detail)

    def unit(self) -> str | None:
        """The unit printed with the quantity, if any: "2 strips" -> "strip"."""
        return parse_count(self.detail)[1]


def _same_unit(row: BillRow, unit: str) -> bool:
    """Whether the line counts the same thing as the reference.

    "2 strips" of a tablet priced per tablet is 30 tablets, not 2, so a
    printed unit must match. With no unit printed, a vial or bottle count is
    taken as it stands, but tablets and capsules are sold in strips, so a bare
    count of them is left unchecked rather than read as single tablets.
    """
    printed = row.unit()
    if printed is not None:
        return printed == unit
    return unit not in PACKED_UNITS


@dataclass(frozen=True)
class Flag:
    kind: FlagKind
    level: FlagLevel
    row_position: int
    billed: Decimal
    reference_amount: Decimal
    reference_source: str
    excess: Decimal
    reference_detail: dict = field(default_factory=dict)


def _above_mrp(row: BillRow, references: ReferenceData) -> Flag | None:
    price = references.price_for(row.name)
    if price is None or (price.mrp is None and price.nppa_ceiling is None):
        return None

    count = row.count()
    if count is None or count <= 0 or row.amount <= 0 or not _same_unit(row, price.unit):
        return None

    ceiling, source = price.ceiling()
    unit_price = row.amount / count
    if unit_price <= ceiling:
        return None

    allowed = _money(ceiling * count)
    return Flag(
        kind="above_mrp",
        level="red",
        row_position=row.position,
        billed=_money(row.amount),
        reference_amount=allowed,
        reference_source=source,
        excess=_money(row.amount - allowed),
        reference_detail={
            "reference_name": price.name,
            "unit": price.unit,
            "unit_price_billed": str(_money(unit_price)),
            "unit_price_reference": str(_money(ceiling)),
            "quantity": _count(count),
            "list": price.source,
        },
    )


def _duplicates(rows: list[BillRow]) -> list[Flag]:
    """Flags every repeat after the first identical line.

    Identical means the same item and the same printed date or time, so two
    genuine visits on different days are left alone, while the same visit
    entered twice for 11 Oct 10:30 am is not. A repeat without a date or time
    ("1 vial" twice) is usually two doses, so it is never called a duplicate.
    """
    seen: dict[tuple[str, str], BillRow] = {}
    flags: list[Flag] = []
    for row in rows:
        if not is_timed(row.detail):
            continue
        key = (normalize(row.name), normalize(row.detail))
        first = seen.get(key)
        if first is None:
            seen[key] = row
            continue
        flags.append(
            Flag(
                kind="duplicate",
                level="red",
                row_position=row.position,
                billed=_money(row.amount),
                # One of them should be there; the repeat is the excess.
                reference_amount=_money(first.amount),
                reference_source="duplicate",
                excess=_money(row.amount),
                reference_detail={
                    "first_row_position": first.position,
                    "repeated_detail": row.detail,
                },
            )
        )
    return flags


def _unusual_quantity(row: BillRow, references: ReferenceData) -> Flag | None:
    norm = references.norm_for(row.name)
    if norm is None:
        return None

    count = row.count()
    if count is None or count <= norm.usual_max_per_day or row.amount <= 0:
        return None
    # "2 boxes" of gloves says nothing about pairs. Amber is only a question,
    # so a bare count is still compared; a different unit is not.
    printed = row.unit()
    if printed is not None and printed != norm.unit:
        return None

    unit_price = row.amount / count
    usual_cost = _money(unit_price * norm.usual_max_per_day)
    return Flag(
        kind="quantity",
        level="amber",
        row_position=row.position,
        billed=_money(row.amount),
        reference_amount=usual_cost,
        reference_source="quantity_norm",
        excess=_money(row.amount - usual_cost),
        reference_detail={
            "reference_name": norm.name,
            "unit": norm.unit,
            "quantity": _count(count),
            "usual_max_per_day": _count(norm.usual_max_per_day),
            "list": norm.source,
        },
    )


def audit_bill(rows: list[BillRow], references: ReferenceData) -> list[Flag]:
    """Runs every check over one day's bill.

    Red flags come first, then amber, because a family reading this in a
    hospital corridor should see the clear-cut ones first. Within a level the
    bill's own order is kept, so a flag is easy to find on the page.
    """
    flags: list[Flag] = _duplicates(rows)
    duplicate_rows = {flag.row_position for flag in flags}

    for row in rows:
        # A duplicated line is already answered by removing the repeat; checking
        # its unit price as well would ask the family two questions about one
        # mistake.
        if row.position in duplicate_rows:
            continue
        if above := _above_mrp(row, references):
            flags.append(above)
        elif unusual := _unusual_quantity(row, references):
            flags.append(unusual)

    order = {"red": 0, "amber": 1}
    flags.sort(key=lambda flag: (order[flag.level], flag.row_position))
    return flags


def total_excess(flags: list[Flag]) -> Decimal:
    return _money(sum((flag.excess for flag in flags), Decimal("0")))
