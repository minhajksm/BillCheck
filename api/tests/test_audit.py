"""The audit logic: price matching, duplicate detection, quantity norms.

The worked examples are the ones in docs/prototype.html, so the numbers here
and the numbers on screen stay in step.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from audit import BillRow, audit_bill, total_excess
from references import ReferenceData, load_reference_data, normalize, parse_quantity

REFERENCES = load_reference_data(Path(__file__).resolve().parents[2] / "data/samples/reference-prices.json")


def row(position: int, name: str, detail: str | None, amount: str, quantity: str | None = None) -> BillRow:
    return BillRow(
        position=position,
        name=name,
        detail=detail,
        quantity=None if quantity is None else Decimal(quantity),
        amount=Decimal(amount),
    )


# --- the pieces --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Inj. Meropenem 1g", "inj meropenem 1g"),
        ("IV fluid, Ringer lactate 500ml", "iv fluid ringer lactate 500ml"),
        ("  Surgical   gloves  ", "surgical gloves"),
    ],
)
def test_normalize(raw: str, expected: str):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("6 vials", Decimal("6")),
        ("80 pairs", Decimal("80")),
        ("1 day", Decimal("1")),
        ("2.5 litres", Decimal("2.5")),
        # Bills print dates and counts in the same column. A date is not a
        # count: reading this as eleven of something turns one consultant
        # visit into a quantity to question.
        ("11 Oct, 10:30 am", None),
        ("9 October", None),
        ("11/10/2026", None),
        (None, None),
        ("one set", None),
    ],
)
def test_parse_quantity(detail: str | None, expected: Decimal | None):
    assert parse_quantity(detail) == expected


def test_prefers_the_most_specific_alias():
    """A 1g vial must not be checked against a bare "meropenem" entry if a
    more specific one exists."""
    price = REFERENCES.price_for("Inj. Meropenem 1g")
    assert price is not None and price.name == "Meropenem 1g injection"


def test_unknown_items_have_no_reference():
    assert REFERENCES.price_for("Room rent, twin sharing") is None
    assert REFERENCES.norm_for("Room rent, twin sharing") is None


def test_nppa_ceiling_wins_when_lower_than_mrp():
    """Where a drug is under price control the ceiling is the legal maximum,
    so it is checked against even when the printed MRP is higher."""
    price = REFERENCES.price_for("Tab. Paracetamol 650mg")
    assert price is not None and price.mrp == Decimal("2.5")
    amount, source = price.ceiling()
    assert (amount, source) == (Decimal("2.2"), "nppa")


# --- above MRP ---------------------------------------------------------------


def test_flags_a_medicine_billed_above_mrp():
    """The prototype's example: 6 vials at ₹2,950 against a printed MRP of
    ₹1,840, so ₹6,660 over."""
    flags = audit_bill([row(1, "Inj. Meropenem 1g", "6 vials", "17700")], REFERENCES)

    (flag,) = flags
    assert flag.kind == "above_mrp"
    assert flag.level == "red"
    assert flag.billed == Decimal("17700.00")
    assert flag.reference_amount == Decimal("11040.00")
    assert flag.excess == Decimal("6660.00")
    assert flag.reference_source == "mrp"
    assert flag.reference_detail["unit_price_billed"] == "2950.00"
    assert flag.reference_detail["unit_price_reference"] == "1840.00"
    assert flag.reference_detail["quantity"] == "6"


def test_does_not_flag_a_medicine_at_or_below_mrp():
    assert audit_bill([row(1, "Inj. Meropenem 1g", "6 vials", "11040")], REFERENCES) == []
    assert audit_bill([row(1, "Inj. Meropenem 1g", "6 vials", "9000")], REFERENCES) == []


def test_uses_the_quantity_column_when_the_bill_has_one():
    flags = audit_bill([row(1, "Inj. Meropenem 1g", "as charged", "17700", quantity="6")], REFERENCES)
    assert flags[0].excess == Decimal("6660.00")


def test_ignores_items_with_no_usable_quantity():
    assert audit_bill([row(1, "Inj. Meropenem 1g", None, "17700")], REFERENCES) == []


def test_ignores_zero_and_negative_amounts():
    """Discount and write-off lines are not overcharges."""
    assert audit_bill([row(1, "Inj. Meropenem 1g", "6 vials", "0")], REFERENCES) == []
    assert audit_bill([row(1, "Inj. Meropenem 1g", "6 vials", "-500")], REFERENCES) == []


# --- duplicates --------------------------------------------------------------


def test_flags_the_repeat_of_an_identical_line():
    flags = audit_bill(
        [
            row(1, "Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", "2500"),
            row(2, "Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", "2500"),
        ],
        REFERENCES,
    )

    (flag,) = flags
    assert (flag.kind, flag.level, flag.row_position) == ("duplicate", "red", 2)
    assert flag.excess == Decimal("2500.00")
    assert flag.reference_detail["first_row_position"] == 1


def test_does_not_flag_the_same_visit_on_different_days():
    flags = audit_bill(
        [
            row(1, "Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", "2500"),
            row(2, "Consultant visit, Dr. A. Mehta", "12 Oct, 10:30 am", "2500"),
        ],
        REFERENCES,
    )
    assert flags == []


def test_flags_every_repeat_after_the_first():
    flags = audit_bill(
        [
            row(1, "Dressing charge", "11 Oct", "400"),
            row(2, "Dressing charge", "11 Oct", "400"),
            row(3, "Dressing charge", "11 Oct", "400"),
        ],
        REFERENCES,
    )
    assert [flag.row_position for flag in flags] == [2, 3]
    assert total_excess(flags) == Decimal("800.00")


def test_a_duplicate_is_asked_about_once():
    """A duplicated line is answered by removing the repeat. Checking its unit
    price too would ask the family two questions about one mistake."""
    flags = audit_bill(
        [
            row(1, "Inj. Meropenem 1g", "6 vials", "17700"),
            row(2, "Inj. Meropenem 1g", "6 vials", "17700"),
        ],
        REFERENCES,
    )
    # Both are red, so they come back in the bill's own order. What matters is
    # that row 2 carries only the duplicate flag, not an above-MRP one as well.
    assert [(flag.kind, flag.row_position) for flag in flags] == [
        ("above_mrp", 1),
        ("duplicate", 2),
    ]
    assert [flag.kind for flag in flags if flag.row_position == 2] == ["duplicate"]


# --- quantity norms ----------------------------------------------------------


def test_flags_an_unusual_quantity_as_amber():
    """The prototype's example: 80 pairs of gloves against a usual 20."""
    flags = audit_bill([row(1, "Surgical gloves", "80 pairs", "6800")], REFERENCES)

    (flag,) = flags
    assert flag.kind == "quantity"
    assert flag.level == "amber", "an unusual quantity is a question, never a verdict"
    assert flag.reference_amount == Decimal("1700.00")
    assert flag.excess == Decimal("5100.00")
    assert flag.reference_detail["usual_max_per_day"] == "20"
    assert flag.reference_detail["quantity"] == "80"


def test_does_not_flag_a_normal_quantity():
    assert audit_bill([row(1, "Surgical gloves", "20 pairs", "1700")], REFERENCES) == []
    assert audit_bill([row(1, "Surgical gloves", "8 pairs", "680")], REFERENCES) == []


# --- the whole bill ----------------------------------------------------------


def prototype_bill() -> list[BillRow]:
    """The day 3 bill from docs/prototype.html."""
    return [
        row(1, "Room rent, twin sharing", "1 day", "6500"),
        row(2, "Nursing charges", "1 day", "2200"),
        row(3, "Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", "2500"),
        row(4, "Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", "2500"),
        row(5, "Inj. Meropenem 1g", "6 vials", "17700"),
        row(6, "Inj. Pantoprazole 40mg", "2 vials", "120"),
        row(7, "IV fluid, Ringer lactate 500ml", "4 bottles", "520"),
        row(8, "CBC and CRP tests", "1 set", "1450"),
        row(9, "Chest X-ray", "1 view", "950"),
        row(10, "Surgical gloves", "80 pairs", "6800"),
        row(11, "Syringes and IV cannula", "1 set", "1250"),
    ]


def test_audits_the_whole_prototype_bill():
    flags = audit_bill(prototype_bill(), REFERENCES)

    assert [(flag.kind, flag.row_position) for flag in flags] == [
        ("duplicate", 4),
        ("above_mrp", 5),
        ("quantity", 10),
    ], "red flags first, then amber, each in the bill's own order"
    assert total_excess(flags) == Decimal("14260.00")


def test_leaves_ordinary_charges_alone():
    """Eight of the eleven lines are within range, and a family must not be
    sent to the billing desk over a room rent that is simply a room rent."""
    flagged = {flag.row_position for flag in audit_bill(prototype_bill(), REFERENCES)}
    assert flagged == {4, 5, 10}


def test_an_entirely_ordinary_bill_raises_nothing():
    rows = [
        row(1, "Room rent, twin sharing", "1 day", "6500"),
        row(2, "Nursing charges", "1 day", "2200"),
        row(3, "Chest X-ray", "1 view", "950"),
    ]
    assert audit_bill(rows, REFERENCES) == []


def test_empty_bill():
    assert audit_bill([], REFERENCES) == []
    assert total_excess([]) == Decimal("0.00")


def test_no_reference_data_means_no_flags():
    """With empty lists nothing is checkable, so nothing is claimed."""
    empty = ReferenceData(prices=(), quantity_norms=())
    flags = audit_bill(prototype_bill(), empty)
    assert [flag.kind for flag in flags] == ["duplicate"], "duplicates need no price list"
